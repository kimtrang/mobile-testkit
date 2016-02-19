import os
import re
import sys
import json
import time

import ansible.inventory
from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager

from requests.exceptions import ConnectionError

from lib.syncgateway import SyncGateway
from lib.sgaccel import SgAccel
from lib.server import Server
from lib.admin import Admin
from lib import settings
from lib.constants import RunMode

from provision.ansible_runner import run_ansible_playbook

import logging
log = logging.getLogger(settings.LOGGER)


class Cluster:

    def __init__(self):

        # get hosts
        cbs_host_vars = self._hosts_for_tag("couchbase_servers")
        sgs_host_vars = self._hosts_for_tag("sync_gateways")
        sgsw_host_vars = self._hosts_for_tag("sync_gateway_index_writers")
        lds_host_vars = self._hosts_for_tag("load_generators")

        # provide simple consumable dictionaries to functional framwork
        cbs = [{"name": cbsv["inventory_hostname"], "ip": cbsv["ansible_host"]} for cbsv in cbs_host_vars]

        # Only collect sync_gateways that are not index_writers
        sgvs = [sgv for sgv in sgs_host_vars if "sync_gateway_index_writers" not in sgv["group_names"]]
        sgs = [{"name": sgv["inventory_hostname"], "ip": sgv["ansible_host"]} for sgv in sgvs]

        sgsw = [{"name": sgwv["inventory_hostname"], "ip": sgwv["ansible_host"]} for sgwv in sgsw_host_vars]
        lds = [{"name": ldv["inventory_hostname"], "ip": ldv["ansible_host"]} for ldv in lds_host_vars]

        self.sync_gateways = [SyncGateway(sg) for sg in sgs]
        self.sg_accels = [SgAccel(sgw) for sgw in sgsw]
        self.servers = [Server(cb) for cb in cbs]
        self.load_generators = lds

        self.current_sg_config_name = ""

    def _hosts_for_tag(self, tag):
        hostfile = "provisioning_config"

        if not os.path.isfile(hostfile):
            log.error("File 'provisioning_config' not found at {}".format(os.getcwd()))
            sys.exit(1)

        variable_manager = VariableManager()
        loader = DataLoader()

        i = ansible.inventory.Inventory(loader=loader, variable_manager=variable_manager, host_list=hostfile)
        variable_manager.set_inventory(i)

        group = i.get_group(tag)
        if group is None:
            return []
        hosts = group.get_hosts()
        return [host.get_vars() for host in hosts]

    def validate_cluster(self):

        # Validate sync gateways
        if len(self.sync_gateways) == 0:
            raise Exception("Functional tests require at least 1 index reader")

    def reset(self, config, run_opts):

        self.validate_cluster()

        # Detect if run mode has changed and reset accordlingly
        existing_buckets = self.servers[0].get_buckets()

        # Parse config and grab bucket names
        conf_path = os.path.abspath("conf/" + config)
        bucket_names_from_config = self.get_bucket_names_from_conf(conf_path)

        # Buckets may be shared for different functionality
        bucket_name_set = list(set(bucket_names_from_config))

        # Validate bucket names
        self.validate_config_bucket_names(run_opts, bucket_name_set)

        # Check if server should reset its buckets
        reset = self.should_server_reset(run_opts, existing_buckets)

        # Check if the passed config already deployed
        log.info("Current config: {}".format(self.current_sg_config_name))
        log.info("New config: {}".format(config))
        should_deploy_config = True

        # If the passed config is the same as the deployed config and a reset is not required, skip deploying the new config
        if self.current_sg_config_name == config and not reset:
            should_deploy_config = False

        self.current_sg_config_name = config
        log.info("Deploying config?: {}".format(should_deploy_config))

        if should_deploy_config:
            # Stop sync_gateways
            log.info(">>> Stopping sync_gateway")
            status = run_ansible_playbook("stop-sync-gateway.yml", stop_on_fail=False)
            assert(status == 0)

        if should_deploy_config:
            # Stop sg_accels
            log.info(">>> Stopping sg_accel")
            status = run_ansible_playbook("stop-sg-accel.yml", stop_on_fail=False)
            assert(status == 0)

        if should_deploy_config:
            # Deleting sync_gateway artifacts
            log.info(">>> Deleting sync_gateway artifacts")
            status = run_ansible_playbook("delete-sync-gateway-artifacts.yml", stop_on_fail=False)
            assert(status == 0)

        if run_opts.mode == RunMode.distributed_index and should_deploy_config:
            # Deleting sg_accel artifacts
            log.info(">>> Deleting sg_accel artifacts")
            status = run_ansible_playbook("delete-sg-accel-artifacts.yml", stop_on_fail=False)
            assert(status == 0)

        if reset:
            # Delete buckets
            log.info(">>> Deleting buckets on: {}".format(self.servers[0].ip))
            existing_buckets = self.servers[0].get_buckets()
            self.servers[0].delete_buckets(existing_buckets)

        if reset:
            log.info(">>> Creating buckets on: {}".format(self.servers[0].ip))
            log.info(">>> Creating buckets {}".format(bucket_name_set))
            self.servers[0].create_buckets(bucket_name_set)

        if should_deploy_config:
            # Start sync-gateway
            log.info(">>> Starting sync_gateway with configuration: {}".format(conf_path))
            status = run_ansible_playbook(
                "start-sync-gateway.yml",
                extra_vars="sync_gateway_config_filepath={0}".format(conf_path),
                stop_on_fail=False
            )
            assert(status == 0)

        # HACK - only enable sg_accel for distributed index tests
        # revise this with https://github.com/couchbaselabs/sync-gateway-testcluster/issues/222
        if run_opts.mode == RunMode.distributed_index and should_deploy_config:
            # Start sg-accel
            status = run_ansible_playbook(
                "start-sg-accel.yml",
                extra_vars="sync_gateway_config_filepath={0}".format(conf_path),
                stop_on_fail=False
            )
            assert(status == 0)

        # Validate CBGT
        if run_opts.mode == RunMode.distributed_index:
            if not self.validate_cbgt_pindex_distribution_retry(run_opts.id):
                self.save_cbgt_diagnostics(run_opts.id)
                raise Exception("Failed to validate CBGT Pindex distribution")
            log.info(">>> Detected valid CBGT Pindex distribution")
        else:
            log.info(">>> Running in channel cache")

        return run_opts.mode

    def get_bucket_names_from_conf(self, conf_path):

        bucket_names = []

        with open(conf_path, "r") as config:
            data = config.read()

            # strip out templated variables {{ ... }}
            data = re.sub("({{.*}})", "0", data)

            # strip out sync functions `function ... }`
            data = re.sub("(`function.*\n)(.*\n)+(.*}`)", "0", data)

            # Find all bucket names in config's databases: {}
            conf_obj = json.loads(data)

            # Add CBGT buckets
            if "cluster_config" in conf_obj.keys():
                bucket_names.append(conf_obj["cluster_config"]["bucket"])

            dbs = conf_obj["databases"]
            for key, val in dbs.iteritems():
                # Add data buckets
                bucket_names.append(val["bucket"])
                if "channel_index" in val:
                    # index buckets
                    bucket_names.append(val["channel_index"]["bucket"])

        return bucket_names

    def validate_config_bucket_names(self, mode, config_bucket_names):

        if ((mode == RunMode.channel_cache and len(config_bucket_names) > 1) or
                (mode == RunMode.distributed_index and len(config_bucket_names) > 2)):
            # Multiple buckets scenario
            return

        if mode == RunMode.channel_cache:
            assert(len(config_bucket_names) == 1 and "data-bucket" in config_bucket_names)
        elif mode == RunMode.distributed_index:
            assert(len(config_bucket_names) == 2 and "data-bucket" in config_bucket_names and "index-bucket" in config_bucket_names)

    def should_server_reset(self, run_opts, existing_buckets):

        reset = False

        if run_opts.reset:
            log.info("run_opts.reset == True. Cleaning!")
            reset = True
        elif len(existing_buckets) != 1 and run_opts.mode == RunMode.channel_cache:
            log.info("Incorrect number of buckets for 'CC' mode. Reseting!")
            reset = True
        elif len(existing_buckets) != 2 and run_opts.mode == RunMode.distributed_index:
            log.info("Incorrect number of buckets for 'DI' mode. Reseting!")
            reset = True
        elif run_opts.mode == RunMode.distributed_index and "index-bucket" not in existing_buckets:
            log.info("Mode has changed. Reseting!")
            reset = True
        elif run_opts.mode == RunMode.channel_cache and "index-bucket" in existing_buckets:
            log.info("Mode has changed. Reseting!")
            reset = True

        return reset

    def save_cbgt_diagnostics(self, test_id):
        
        # CBGT REST Admin API endpoint
        for sync_gateway_writer in self.sg_accels:

            adminApi = Admin(sync_gateway_writer, test_id)
            cbgt_diagnostics = adminApi.get_cbgt_diagnostics()
            cbgt_cfg = adminApi.get_cbgt_cfg()
        
            # dump raw diagnostics
            pretty_print_json = json.dumps(cbgt_diagnostics, sort_keys=True, indent=4, separators=(',', ': '))
            log.info("SG {} CBGT diagnostic output: {}".format(sync_gateway_writer, pretty_print_json))
        
    def validate_cbgt_pindex_distribution_retry(self, test_id):
        """
        Validates the CBGT pindex distribution by looking for nodes that don't have
        any pindexes assigned to it
        """
        for i in xrange(10):
            is_valid = self.validate_cbgt_pindex_distribution(test_id)
            if is_valid:
               return True
            else:
                log.error("Could not validate CBGT Pindex distribution.  Will retry after sleeping ..")
                time.sleep(5)

        return False 

    def validate_cbgt_pindex_distribution(self, test_id):

        # build a map of node -> num_pindexes
        node_defs_pindex_counts = {}

        # CBGT REST Admin API endpoint 
        adminApi = Admin(self.sg_accels[0], test_id)
        cbgt_cfg = adminApi.get_cbgt_cfg()

        # loop over the planpindexes and update the count for the node where it lives
        # this will end up with a dictionary like:
        #  {'74c818f04b99b169': 32, '11886131c807a30e': 32}  (each node uuid has 32 pindexes)
        plan_pindexes = cbgt_cfg["planPIndexes"]["planPIndexes"]
        for data_bucket_key, data_bucket_val in plan_pindexes.iteritems():

            # get the nodes where this pindex lives
            nodes = data_bucket_val["nodes"]
            # it should only live on one node.  if not, abort.
            if len(nodes) > 1:
                raise Exception("Unexpected: a CBGT Pindex was assigned to more than one node")
            # loop over the nodes where this pindex lives and increment the count
            for node in nodes:

                # add a key for this node if we don't already have one
                if not node_defs_pindex_counts.has_key(node):
                    node_defs_pindex_counts[node] = 0
                    
                current_pindex_count = node_defs_pindex_counts[node]
                current_pindex_count += 1
                node_defs_pindex_counts[node] = current_pindex_count

        log.info("CBGT node to pindex counts: {}".format(node_defs_pindex_counts))
        
        # make sure number of unique node uuids is equal to the number of sync gateway writers
        if len(node_defs_pindex_counts) != len(self.sg_accels):
            log.error("CBGT len(unique_node_uuids) != len(self.sync_gateway_writers) ({} != {})".format(
                len(node_defs_pindex_counts),
                len(self.sg_accels)
            ))
            return False 

        # make sure that all of the nodes have approx the same number of pindexes assigneed to them
        i = 0
        num_pindex_first_node = 0 
        for node_def_uuid, num_pindexes in node_defs_pindex_counts.iteritems():

            if i == 0:
                # it's the first node we've looked at, just record number of pindexes and continue 
                num_pindex_first_node = num_pindexes
                i += 1
                continue

            # ok, it's the 2nd+ node, make sure the delta with the first node is less than or equal to 1
            # (the reason we can't compare for equality is that sometimes the pindexes can't be
            # divided evenly across the cluster)
            delta = abs(num_pindex_first_node - num_pindexes)
            if delta > 1:
                log.info("CBGT Sync Gateway node {} has {} pindexes, but other node has {} pindexes.".format(
                    node_def_uuid,
                    num_pindexes,
                    num_pindex_first_node
                ))
                return False
                
    
        return True

    def verify_alive(self, mode):
        errors = []
        for sg in self.sync_gateways:
            try:
                info = sg.info()
                log.info("sync_gateway: {}, info: {}".format(sg.url, info))
            except ConnectionError as e:
                log.error("sync_gateway down: {}".format(e))
                errors.append((sg, e))

        if mode == RunMode.distributed_index:
            for sa in self.sg_accels:
                try:
                    info = sa.info()
                    log.info("sg_accel: {}, info: {}".format(sa.url, info))
                except ConnectionError as e:
                    log.error("sg_accel down: {}".format(e))
                    errors.append((sa, e))

        return errors

    def __repr__(self):
        s = "\n\n"
        s += "Sync Gateways\n"
        for sg in self.sync_gateways:
            s += str(sg)
        s += "\nSync Gateway Accels\n"
        for sgw in self.sg_accels:
            s += str(sgw)
        s += "\nCouchbase Servers\n"
        for server in self.servers:
            s += str(server)
        s += "\nLoad Generators\n"
        for lg in self.load_generators:
            s += str(lg)
        s += "\n"
        return s
