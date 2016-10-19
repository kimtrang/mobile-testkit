import time

import concurrent.futures

from testkit.admin import Admin
from testkit.cluster import Cluster
from testkit.verify import verify_changes
from testkit.verify import verify_same_docs

from keywords.utils import log_info


def continuous_changes_parametrized(cluster_conf, sg_conf, num_users, num_docs, num_revisions):

    log_info("Running 'continuous_changes_parametrized'")
    log_info("cluster_conf: {}".format(cluster_conf))
    log_info("sg_conf: {}".format(sg_conf))
    log_info("num_users: {}".format(num_users))
    log_info("num_docs: {}".format(num_docs))
    log_info("num_revisions: {}".format(num_revisions))

    cluster = Cluster(config=cluster_conf)
    mode = cluster.reset(sg_config_path=sg_conf)

    admin = Admin(cluster.sync_gateways[0])
    users = admin.register_bulk_users(target=cluster.sync_gateways[0], db="db", name_prefix="user", number=num_users, password="password", channels=["ABC", "TERMINATE"])
    abc_doc_pusher = admin.register_user(target=cluster.sync_gateways[0], db="db", name="abc_doc_pusher", password="password", channels=["ABC"])
    doc_terminator = admin.register_user(target=cluster.sync_gateways[0], db="db", name="doc_terminator", password="password", channels=["TERMINATE"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:

        futures = {executor.submit(user.start_continuous_changes_tracking, termination_doc_id="killcontinuous"): user.name for user in users}
        futures[executor.submit(abc_doc_pusher.add_docs, num_docs)] = "doc_pusher"

        for future in concurrent.futures.as_completed(futures):
            task_name = futures[future]

            # Send termination doc to seth continuous changes feed subscriber
            if task_name == "doc_pusher":
                try:
                    errors = future.result()
                    assert len(errors) == 0
                except Exception as exc:
                    print("ERROR PUSHING DOCS: {}".format(str(exc.value)))
                    raise AssertionError("Pushing docs failed")
                update_errors = abc_doc_pusher.update_docs(num_revs_per_doc=num_revisions)
                if len(update_errors) != 0:
                    raise AssertionError("Updating failed!!: {}".format(update_errors))

                print("Sleeping")

                time.sleep(10)

                print("Pushing terminator doc.")

                doc_terminator.add_doc("killcontinuous")
            elif task_name.startswith("user"):
                # When the user has continuous _changes feed closed, return the docs and verify the user got all the channel docs
                try:
                    docs_in_changes = future.result()
                except Exception as exc:
                    print("ERROR getting changes: {}".format(str(exc.value)))
                    raise AssertionError("getting changes failed")
                # Expect number of docs + the termination doc + _user doc
                print("Verifying user: {}".format(task_name))
                verify_same_docs(expected_num_docs=num_docs, doc_dict_one=docs_in_changes, doc_dict_two=abc_doc_pusher.cache)

    # Expect number of docs + the termination doc
    verify_changes(abc_doc_pusher, expected_num_docs=num_docs, expected_num_revisions=num_revisions, expected_docs=abc_doc_pusher.cache)

    # Verify all sync_gateways are running
    errors = cluster.verify_alive(mode)
    assert len(errors) == 0


def continuous_changes_sanity(cluster_conf, sg_conf, num_docs, num_revisions):

    log_info("Running 'continuous_changes_sanity'")
    log_info("cluster_conf: {}".format(cluster_conf))
    log_info("sg_conf: {}".format(sg_conf))
    log_info("num_docs: {}".format(num_docs))
    log_info("num_revisions: {}".format(num_revisions))

    cluster = Cluster(config=cluster_conf)
    mode = cluster.reset(sg_config_path=sg_conf)

    admin = Admin(cluster.sync_gateways[0])
    seth = admin.register_user(target=cluster.sync_gateways[0], db="db", name="seth", password="password", channels=["ABC", "TERMINATE"])
    abc_doc_pusher = admin.register_user(target=cluster.sync_gateways[0], db="db", name="abc_doc_pusher", password="password", channels=["ABC"])
    doc_terminator = admin.register_user(target=cluster.sync_gateways[0], db="db", name="doc_terminator", password="password", channels=["TERMINATE"])

    docs_in_changes = dict()

    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:

        futures = dict()
        futures[executor.submit(seth.start_continuous_changes_tracking, termination_doc_id="killcontinuous")] = "continuous"
        futures[executor.submit(abc_doc_pusher.add_docs, num_docs)] = "doc_pusher"

        for future in concurrent.futures.as_completed(futures):
            task_name = futures[future]

            # Send termination doc to seth continuous changes feed subscriber
            if task_name == "doc_pusher":
                abc_doc_pusher.update_docs(num_revs_per_doc=num_revisions)

                time.sleep(5)

                doc_terminator.add_doc("killcontinuous")
            elif task_name == "continuous":
                docs_in_changes = future.result()

    # Expect number of docs + the termination doc
    verify_changes(abc_doc_pusher, expected_num_docs=num_docs, expected_num_revisions=num_revisions, expected_docs=abc_doc_pusher.cache)

    # Expect number of docs + the termination doc + _user doc
    verify_same_docs(expected_num_docs=num_docs, doc_dict_one=docs_in_changes, doc_dict_two=abc_doc_pusher.cache)

    # Verify all sync_gateways are running
    errors = cluster.verify_alive(mode)
    assert len(errors) == 0
