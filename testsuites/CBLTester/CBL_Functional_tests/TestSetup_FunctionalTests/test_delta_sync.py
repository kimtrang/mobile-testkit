import pytest
import time

from keywords.MobileRestClient import MobileRestClient
from keywords.utils import log_info
from keywords.utils import random_string
from CBLClient.Replication import Replication
from CBLClient.Authenticator import Authenticator
from utilities.cluster_config_utils import persist_cluster_config_environment_prop, copy_to_temp_conf
from keywords.SyncGateway import sync_gateway_config_path_for_mode
from libraries.testkit import cluster


@pytest.mark.sanity
@pytest.mark.listener
@pytest.mark.syncgateway
@pytest.mark.replication
@pytest.mark.parametrize("num_of_docs, replication_type, file_attachment, continuous", [
    # (10, "pull", None, True),
    (10, "pull", "sample_text.txt", True),
    # (10, "push", "sample_text.txt", True),
    # (10, "push", None, True)
])
def test_delta_sync_replication(params_from_base_test_setup, num_of_docs, replication_type, file_attachment, continuous):
    '''
    @summary:
    1. Create docs in CBL
    2. Do push_pull replication
    3. update docs in SGW  with/without attachment
    4. Do push/pull replication
    5. Verify delta sync stats shows bandwidth saving, replication count, number of docs updated using delta sync
    '''
    sg_db = "db"
    sg_url = params_from_base_test_setup["sg_url"]
    sg_admin_url = params_from_base_test_setup["sg_admin_url"]
    cluster_config = params_from_base_test_setup["cluster_config"]
    sg_blip_url = params_from_base_test_setup["target_url"]
    base_url = params_from_base_test_setup["base_url"]
    sg_config = params_from_base_test_setup["sg_config"]
    db = params_from_base_test_setup["db"]
    cbl_db = params_from_base_test_setup["source_db"]
    sync_gateway_version = params_from_base_test_setup["sync_gateway_version"]
    mode = params_from_base_test_setup["mode"]

    if sync_gateway_version < "2.5.0":
        pytest.skip('This test cannnot run with sg version below 2.5')
    channels = ["ABC"]
    username = "autotest"
    password = "password"
    number_of_updates = 1

    # Reset cluster to ensure no data in system
    c = cluster.Cluster(config=cluster_config)
    c.reset(sg_config_path=sg_config)
    enable_delta_sync(c, sg_config, cluster_config, mode, True)

    sg_client = MobileRestClient()
    sg_client.create_user(sg_admin_url, sg_db, username, password=password, channels=channels)
    cookie, session_id = sg_client.create_session(sg_admin_url, sg_db, username)
    session = cookie, session_id
    # 1. Create docs in CBL
    db.create_bulk_docs(num_of_docs, "cbl_sync", db=cbl_db, channels=channels)

    # 2. Do push replication
    replicator = Replication(base_url)
    authenticator = Authenticator(base_url)
    replicator_authenticator = authenticator.authentication(session_id, cookie, authentication_type="session")
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=continuous,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type="push")
    replicator.stop(repl)
    doc_reads_bytes, doc_writes_bytes = get_net_stats(sg_client, sg_admin_url)
    sg_docs = sg_client.get_all_docs(url=sg_admin_url, db=sg_db, include_docs=True)["rows"]
    # Verify database doc counts
    cbl_doc_count = db.getCount(cbl_db)
    assert len(sg_docs) == cbl_doc_count, "Expected number of docs does not exist in sync-gateway after replication"

    # 3. update docs in SGW  with/without attachment
    for doc in sg_docs:
        sg_client.update_doc(url=sg_url, db=sg_db, doc_id=doc["id"], number_updates=1, auth=session, channels=channels, attachment_name=file_attachment)
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=continuous,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type="pull")
    replicator.stop(repl)
    doc_reads_bytes1, doc_writes_bytes1 = get_net_stats(sg_client, sg_admin_url)
    delta_size = doc_reads_bytes1
    assert delta_size < doc_writes_bytes, "did not replicate just delta"
    """
    if replication_type == "push":
        doc_ids = db.getDocIds(cbl_db)
        cbl_db_docs = db.getDocuments(cbl_db, doc_ids)
        for doc_id, doc_body in cbl_db_docs.items():
            for i in range(number_of_updates):
                doc_body["new_field_1"] = random_string(length=30)
                doc_body["new_field_2"] = random_string(length=80)
                db.updateDocument(database=cbl_db, data=doc_body, doc_id=doc_id, attachments_name=file_attachment)
    else:
        for doc in sg_docs:
            sg_client.update_doc(url=sg_url, db=sg_db, doc_id=doc["id"], number_updates=number_of_updates, auth=session, channels=channels, attachment_name=file_attachment)

    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=continuous,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type=replication_type)
    replicator.stop(repl)

    # Get Sync Gateway Expvars
    expvars = sg_client.get_expvars(url=sg_admin_url)

    if replication_type == "push":
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['delta_push_doc_count'] == num_of_docs, "delta push replication count is not right"
    else:
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['delta_pull_replication_count'] == 2, "delta pull replication count is not right"
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['deltas_requested'] == num_of_docs * 2, "delta pull requested is not equal to number of docs"
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['deltas_sent'] == num_of_docs * 2, "delta pull sent is not equal to number of docs"

    doc_reads_bytes2, doc_writes_bytes2 = get_net_stats(sg_client, sg_admin_url)
    if replication_type == "push":
        delta_size = doc_writes_bytes2 - doc_writes_bytes1
    else:
        delta_size = doc_reads_bytes2 - doc_reads_bytes1

    if replication_type != "push" and file_attachment is not None:
        assert delta_size < doc_writes_bytes, "did not replicate just delta"
    """
    sg_docs = sg_client.get_all_docs(url=sg_admin_url, db=sg_db, include_docs=True)["rows"]
    compare_docs(cbl_db, db, sg_docs)


@pytest.mark.listener
@pytest.mark.syncgateway
@pytest.mark.replication
@pytest.mark.parametrize("num_of_docs, replication_type", [
    (10, "pull"),
    # (10, "push")
])
def test_delta_sync_enabled_disabled(params_from_base_test_setup, num_of_docs, replication_type):
    '''
    @summary:
    1. Have detla sync enabled by default
    2. Create docs in CBL
    3. Do push replication to SGW
    4. update docs in SGW
    5. Do pull replication to CBL
    6. Get stats pub_net_bytes_send
    7. Disable delta sync in sg config and restart SGW
    8. update docs in SGW
    9. Do pull replication to CBL
    10. Verify there is no delta sync stats available on _expvars API
    11. Get stats pub_net_bytes_send
    12 Verify pub_net_bytes_send stats go up high when compared with step #6 as it resplicates full doc
    '''
    sg_db = "db"
    sg_url = params_from_base_test_setup["sg_url"]
    sg_admin_url = params_from_base_test_setup["sg_admin_url"]
    cluster_config = params_from_base_test_setup["cluster_config"]
    sg_blip_url = params_from_base_test_setup["target_url"]
    base_url = params_from_base_test_setup["base_url"]
    sg_config = params_from_base_test_setup["sg_config"]
    db = params_from_base_test_setup["db"]
    cbl_db = params_from_base_test_setup["source_db"]
    mode = params_from_base_test_setup["mode"]
    sync_gateway_version = params_from_base_test_setup["sync_gateway_version"]

    if sync_gateway_version < "2.5.0":
        pytest.skip('This test cannnot run with sg version below 2.5')
    channels = ["ABC"]
    username = "autotest"
    password = "password"
    number_of_updates = 3

    # Reset cluster to ensure no data in system
    c = cluster.Cluster(config=cluster_config)
    c.reset(sg_config_path=sg_config)
    enable_delta_sync(c, sg_config, cluster_config, mode, True)

    sg_client = MobileRestClient()
    sg_client.create_user(sg_admin_url, sg_db, username, password=password, channels=channels)
    cookie, session_id = sg_client.create_session(sg_admin_url, sg_db, username)
    session = cookie, session_id
    replicator = Replication(base_url)
    authenticator = Authenticator(base_url)
    replicator_authenticator = authenticator.authentication(session_id, cookie, authentication_type="session")

    db.create_bulk_docs(num_of_docs, "cbl_sync", db=cbl_db, channels=channels)

    # Configure replication with push
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=True,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type="push")
    replicator.stop(repl)

    sg_docs = sg_client.get_all_docs(url=sg_admin_url, db=sg_db, include_docs=True)["rows"]

    # Get expvars and get original size of document
    doc_reads_bytes, doc_writes_bytes = get_net_stats(sg_client, sg_admin_url)
    full_doc_size = doc_reads_bytes
    print "doc read bytes for first time", doc_reads_bytes
    print "doc writes bytes for first time", doc_writes_bytes
    update_docs(replication_type, cbl_db, db, sg_client, sg_docs, sg_url, sg_db, number_of_updates, session, channels)

    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=True,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type=replication_type)
    replicator.stop(repl)

    # Get expvars and get original size of document
    doc_reads_bytes1, doc_writes_bytes1 = get_net_stats(sg_client, sg_admin_url)
    if replication_type == "pull":
        delta_size = doc_reads_bytes1
    else:
        delta_size = doc_writes_bytes1 - doc_writes_bytes

    # Get Sync Gateway Expvars
    expvars = sg_client.get_expvars(url=sg_admin_url)
    if replication_type == "push":
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['delta_push_doc_count'] == 10, "delta push replication count is not right"
    else:
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['delta_pull_replication_count'] == 1, "delta pull replication count is not right"
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['deltas_requested'] == num_of_docs, "delta pull requested is not equal to number of docs"
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['deltas_sent'] == num_of_docs, "delta pull sent is not equal to number of docs"

    # Now disable delta sync and verify replication happens, but full doc should replicate
    enable_delta_sync(c, sg_config, cluster_config, mode, False)
    time.sleep(10)

    update_docs(replication_type, cbl_db, db, sg_client, sg_docs, sg_url, sg_db, number_of_updates, session, channels)
    # Get expvars and get original size of document
    doc_reads_bytes2, doc_writes_bytes2 = get_net_stats(sg_client, sg_admin_url)

    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=False,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type=replication_type)
    sg_docs = sg_client.get_all_docs(url=sg_admin_url, db=sg_db, include_docs=True)["rows"]

    # Get expvars and get original size of document
    doc_reads_bytes3, doc_writes_bytes3 = get_net_stats(sg_client, sg_admin_url)
    if replication_type == "pull":
        delta_disabled_doc_size = doc_reads_bytes3 - doc_reads_bytes2
    else:
        delta_disabled_doc_size = doc_writes_bytes3 - doc_writes_bytes2

    compare_docs(cbl_db, db, sg_docs)
    # assert delta_disabled_doc_size == full_doc_size, "did not get full doc size"
    assert delta_disabled_doc_size > delta_size, "disabled delta doc size is more than enabled delta size"
    try:
        expvars = sg_client.get_expvars(url=sg_admin_url)
        expvars['syncgateway']['per_db'][sg_db]['delta_sync']
        assert False, "delta sync is not disabled"
    except KeyError:
        assert True


@pytest.mark.syncgateway
@pytest.mark.replication
@pytest.mark.parametrize("num_of_docs, replication_type", [
    (1, "pull"),
    (1, "push")
])
def test_delta_sync_within_expiry(params_from_base_test_setup, num_of_docs, replication_type):
    '''
    @summary:
    1. Have delta sync enabled by default
    2. Create docs in CBL
    3. Do push replication to SGW
    4. update docs in SGW/CBL
    5. replicate docs using pull replication
    6. get pub_net_stats_send from expvar api
    7. update docs in SGW
    8. wait for 2 minutes which makes delta revision expire
    9. replicate docs using pull replication
    10 get pub_net_stats_send from expvar api
    '''
    sg_db = "db"
    sg_url = params_from_base_test_setup["sg_url"]
    sg_admin_url = params_from_base_test_setup["sg_admin_url"]
    cluster_config = params_from_base_test_setup["cluster_config"]
    sg_blip_url = params_from_base_test_setup["target_url"]
    base_url = params_from_base_test_setup["base_url"]
    db = params_from_base_test_setup["db"]
    cbl_db = params_from_base_test_setup["source_db"]
    mode = params_from_base_test_setup["mode"]
    sync_gateway_version = params_from_base_test_setup["sync_gateway_version"]

    if sync_gateway_version < "2.5.0":
        pytest.skip('This test cannnot run with sg version below 2.5')
    channels = ["ABC"]
    username = "autotest"
    password = "password"
    number_of_updates = 3

    # Reset cluster to ensure no data in system
    c = cluster.Cluster(config=cluster_config)
    sg_config = sync_gateway_config_path_for_mode("delta_sync/sync_gateway_delta_sync_2min_rev", mode)
    c.reset(sg_config_path=sg_config)

    sg_client = MobileRestClient()
    sg_client.create_user(sg_admin_url, sg_db, username, password=password, channels=channels)
    cookie, session_id = sg_client.create_session(sg_admin_url, sg_db, username)
    session = cookie, session_id
    # 2. Create docs in CBL
    db.create_bulk_docs(num_of_docs, "cbl_sync", db=cbl_db, channels=channels)

    # 3. Do push replication to SGW
    replicator = Replication(base_url)
    authenticator = Authenticator(base_url)
    replicator_authenticator = authenticator.authentication(session_id, cookie, authentication_type="session")
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=True,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type="push")
    replicator.stop(repl)

    # get stats_send from expvar api
    doc_reads_bytes1, doc_writes_bytes1 = get_net_stats(sg_client, sg_admin_url)

    # 4. update docs in SGW/CBL
    sg_docs = sg_client.get_all_docs(url=sg_url, db=sg_db, include_docs=True, auth=session)["rows"]
    update_docs(replication_type, cbl_db, db, sg_client, sg_docs, sg_url, sg_db, number_of_updates, session, channels)

    # 5. replicate docs using push/pull replication
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=False,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type=replication_type)

    # 6. get stats_send from expvar api
    doc_reads_bytes2, doc_writes_bytes2 = get_net_stats(sg_client, sg_admin_url)
    if replication_type == "pull":
        delta_size = doc_reads_bytes2
    else:
        delta_size = doc_writes_bytes2 - doc_writes_bytes1
    assert delta_size < doc_writes_bytes1, "delta size is not less than expired delta size"
    # 7. update docs in SGW
    sg_docs = sg_client.get_all_docs(url=sg_url, db=sg_db, include_docs=True, auth=session)["rows"]
    update_docs(replication_type, cbl_db, db, sg_client, sg_docs, sg_url, sg_db, number_of_updates, session, channels)

    # 8. wait for 2 minutes which makes delta revision expire and update full doc
    time.sleep(130)

    # 9. replicate docs using pull replication
    replicator.configure_and_replicate(source_db=cbl_db,
                                       target_url=sg_blip_url,
                                       continuous=False,
                                       replicator_authenticator=replicator_authenticator,
                                       replication_type=replication_type)

    # compare full body on SGW and CBL and verify whole body matches
    sg_docs = sg_client.get_all_docs(url=sg_url, db=sg_db, include_docs=True, auth=session)["rows"]
    compare_docs(cbl_db, db, sg_docs)


@pytest.mark.listener
@pytest.mark.syncgateway
@pytest.mark.replication
@pytest.mark.parametrize("num_of_docs, replication_type", [
    (1, "pull"),
    (1, "push")
])
def test_delta_sync_utf8_strings(params_from_base_test_setup, num_of_docs, replication_type):
    '''
    @summary:
    1. Have delta sync enabled by default
    2. Create docs in CBL
    3. Do push replication to SGW
    4. update docs in SGW/CBL with utf8 strings
    5. replicate docs using pull replication
    6. get pub_net_stats_send from expvar api
    7. Verify that docs replicated successfully and only delta is replicated
    '''
    sg_db = "db"
    sg_url = params_from_base_test_setup["sg_url"]
    sg_admin_url = params_from_base_test_setup["sg_admin_url"]
    cluster_config = params_from_base_test_setup["cluster_config"]
    sg_blip_url = params_from_base_test_setup["target_url"]
    base_url = params_from_base_test_setup["base_url"]
    db = params_from_base_test_setup["db"]
    cbl_db = params_from_base_test_setup["source_db"]
    mode = params_from_base_test_setup["mode"]
    sg_config = params_from_base_test_setup["sg_config"]
    sync_gateway_version = params_from_base_test_setup["sync_gateway_version"]

    if sync_gateway_version < "2.5.0":
        pytest.skip('This test cannnot run with sg version below 2.5')
    channels = ["ABC"]
    username = "autotest"
    password = "password"
    number_of_updates = 3

    # Reset cluster to ensure no data in system
    c = cluster.Cluster(config=cluster_config)
    c.reset(sg_config_path=sg_config)
    enable_delta_sync(c, sg_config, cluster_config, mode, True)

    sg_client = MobileRestClient()
    sg_client.create_user(sg_admin_url, sg_db, username, password=password, channels=channels)
    cookie, session_id = sg_client.create_session(sg_admin_url, sg_db, username)
    session = cookie, session_id

    # 2. Create docs in CBL
    db.create_bulk_docs(num_of_docs, "cbl_sync", db=cbl_db, channels=channels)

    # 3. Do push replication to SGW
    replicator = Replication(base_url)
    authenticator = Authenticator(base_url)
    replicator_authenticator = authenticator.authentication(session_id, cookie, authentication_type="session")
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=True,
                                              channels=channels,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type="push")
    replicator.stop(repl)
    doc_reads_bytes1, doc_writes_bytes1 = get_net_stats(sg_client, sg_admin_url)
    full_doc_size = doc_writes_bytes1

    # 4. update docs in SGW/CBL
    sg_docs = sg_client.get_all_docs(url=sg_admin_url, db=sg_db, include_docs=True)["rows"]
    update_docs(replication_type, cbl_db, db, sg_client, sg_docs, sg_url, sg_db, number_of_updates, session, channels, string_type="utf-8")

    # 5. replicate docs using push/pull replication
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=True,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type=replication_type)
    replicator.stop(repl)
    doc_reads_bytes2, doc_writes_bytes2 = get_net_stats(sg_client, sg_admin_url)
    if replication_type == "pull":
        delta_size = doc_reads_bytes2
    else:
        delta_size = doc_writes_bytes2 - doc_writes_bytes1

    compare_docs(cbl_db, db, sg_docs)
    verify_delta_stats_counts(sg_client, sg_admin_url, replication_type, sg_db, num_of_docs)
    assert delta_size < full_doc_size, "delta size is not less than full doc size when delta is replicated"


@pytest.mark.listener
@pytest.mark.syncgateway
@pytest.mark.replication
@pytest.mark.parametrize("num_of_docs, replication_type", [
    (1, "pull"),
    # (1, "push")
])
def test_delta_sync_nested_doc(params_from_base_test_setup, num_of_docs, replication_type):
    '''
    @summary:
    1. Create docs in CBL with nested docs
    2. Do push_pull replication
    3. update docs in SGW
    4. Do push/pull replication
    5. Verify delta sync stats shows bandwidth saving, replication count, number of docs updated using delta sync
    '''
    sg_db = "db"
    sg_url = params_from_base_test_setup["sg_url"]
    sg_admin_url = params_from_base_test_setup["sg_admin_url"]
    cluster_config = params_from_base_test_setup["cluster_config"]
    sg_blip_url = params_from_base_test_setup["target_url"]
    base_url = params_from_base_test_setup["base_url"]
    db = params_from_base_test_setup["db"]
    cbl_db = params_from_base_test_setup["source_db"]
    mode = params_from_base_test_setup["mode"]
    sync_gateway_version = params_from_base_test_setup["sync_gateway_version"]
    sg_config = params_from_base_test_setup["sg_config"]

    if sync_gateway_version < "2.5.0":
        pytest.skip('This test cannnot run with sg version below 2.5')
    channels = ["ABC"]
    username = "autotest"
    password = "password"
    number_of_updates = 3

    # Reset cluster to ensure no data in system
    c = cluster.Cluster(config=cluster_config)
    c.reset(sg_config_path=sg_config)
    enable_delta_sync(c, sg_config, cluster_config, mode, True)

    sg_client = MobileRestClient()
    sg_client.create_user(sg_admin_url, sg_db, username, password=password, channels=channels)
    cookie, session_id = sg_client.create_session(sg_admin_url, sg_db, username)
    session = cookie, session_id

    # 2. Create docs in CBL
    db.create_bulk_docs(num_of_docs, "cbl_sync", db=cbl_db, channels=channels, generator="complex_doc")

    # 3. Do push replication to SGW
    replicator = Replication(base_url)
    authenticator = Authenticator(base_url)
    replicator_authenticator = authenticator.authentication(session_id, cookie, authentication_type="session")
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=True,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type="push")
    replicator.stop(repl)

    # get net_stats_send from expvar api
    doc_reads_bytes1, doc_writes_bytes1 = get_net_stats(sg_client, sg_admin_url)

    # 4. update docs in SGW/CBL
    sg_docs = sg_client.get_all_docs(url=sg_admin_url, db=sg_db, include_docs=True)["rows"]
    update_docs(replication_type, cbl_db, db, sg_client, sg_docs, sg_url, sg_db, number_of_updates, session, channels)

    # 5. replicate docs using pull replication
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=False,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type=replication_type)

    # 6. get pub_net_stats_send from expvar api
    doc_reads_bytes2, doc_writes_bytes2 = get_net_stats(sg_client, sg_admin_url)
    assert doc_reads_bytes2 < doc_writes_bytes1, "delta size is not less than full doc size"

    # 7. Verify the body of nested doc matches with sgw and cbl
    sg_docs = sg_client.get_all_docs(url=sg_admin_url, db=sg_db, include_docs=True)["rows"]
    compare_docs(cbl_db, db, sg_docs)
    verify_delta_stats_counts(sg_client, sg_admin_url, replication_type, sg_db, num_of_docs)


@pytest.mark.syncgateway
@pytest.mark.replication
@pytest.mark.parametrize("num_of_docs, replication_type", [
    (1, "pull"),
    (1, "push")
])
def test_delta_sync_larger_than_doc(params_from_base_test_setup, num_of_docs, replication_type):
    '''
    @summary:
    1. Have delta sync enabled
    2. Create docs in CBL
    3. Do push replication to SGW
    4. get stats from expvar api
    5. update docs in SGW/CBL , update has to be larger than doc in bytes
    6. replicate docs using pull/push replication
    7. get stats from expvar api
    8. Verify full doc is replicated. Delta size at step 7 shold be same as step 4
    '''
    sg_db = "db"
    sg_url = params_from_base_test_setup["sg_url"]
    sg_admin_url = params_from_base_test_setup["sg_admin_url"]
    cluster_config = params_from_base_test_setup["cluster_config"]
    sg_blip_url = params_from_base_test_setup["target_url"]
    base_url = params_from_base_test_setup["base_url"]
    db = params_from_base_test_setup["db"]
    cbl_db = params_from_base_test_setup["source_db"]
    mode = params_from_base_test_setup["mode"]
    sg_config = params_from_base_test_setup["sg_config"]
    sync_gateway_version = params_from_base_test_setup["sync_gateway_version"]

    if sync_gateway_version < "2.5.0":
        pytest.skip('This test cannnot run with sg version below 2.5')
    channels = ["ABC"]
    username = "autotest"
    password = "password"
    number_of_updates = 3

    # Reset cluster to ensure no data in system
    c = cluster.Cluster(config=cluster_config)
    c.reset(sg_config_path=sg_config)
    enable_delta_sync(c, sg_config, cluster_config, mode, True)

    sg_client = MobileRestClient()
    sg_client.create_user(sg_admin_url, sg_db, username, password=password, channels=channels)
    cookie, session_id = sg_client.create_session(sg_admin_url, sg_db, username)
    session = cookie, session_id
    # 2. Create docs in CBL
    db.create_bulk_docs(num_of_docs, "cbl_sync", db=cbl_db, channels=channels)

    # 3. Do push replication to SGW
    replicator = Replication(base_url)
    authenticator = Authenticator(base_url)
    replicator_authenticator = authenticator.authentication(session_id, cookie, authentication_type="session")
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=True,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type="push")
    replicator.stop(repl)

    # get stats_send from expvar api
    doc_reads_bytes1, doc_writes_bytes1 = get_net_stats(sg_client, sg_admin_url)
    full_doc_size = doc_writes_bytes1

    # 4. update docs in SGW/CBL
    sg_docs = sg_client.get_all_docs(url=sg_admin_url, db=sg_db, include_docs=True)["rows"]
    update_larger_doc(replication_type, cbl_db, db, sg_client, sg_docs, sg_url, sg_db, number_of_updates, session, channels)

    # 5. replicate docs using push/pull replication
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=sg_blip_url,
                                              continuous=False,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type=replication_type)

    # 6. get stats from expvar api
    doc_reads_bytes2, doc_writes_bytes2 = get_net_stats(sg_client, sg_admin_url)
    if replication_type == "pull":
        larger_delta_size = doc_reads_bytes2
    else:
        larger_delta_size = doc_writes_bytes2 - doc_writes_bytes1

    # compare full body on SGW and CBL and verify whole body matches
    sg_docs = sg_client.get_all_docs(url=sg_admin_url, db=sg_db, include_docs=True)["rows"]
    compare_docs(cbl_db, db, sg_docs)

    assert larger_delta_size >= full_doc_size, "did not get full doc size after deltas is expired"


def update_docs(replication_type, cbl_db, db, sg_client, sg_docs, sg_url, sg_db, number_of_updates, session, channels, string_type="normal"):
    if replication_type == "push":
        doc_ids = db.getDocIds(cbl_db)
        cbl_db_docs = db.getDocuments(cbl_db, doc_ids)
        for doc_id, doc_body in cbl_db_docs.items():
            if string_type == "utf-8":
                doc_body["new-1"] = unicode(random_string(length=70), "utf-8")
                doc_body["new-2"] = unicode(random_string(length=70), "utf-8")
            else:
                doc_body["new-1"] = random_string(length=70)
                doc_body["new-2"] = random_string(length=30)
            db.updateDocument(database=cbl_db, data=doc_body, doc_id=doc_id)
    else:
        def property_updater(doc_body):
            if string_type == "utf-8":
                doc_body['sg_new_update'] = unicode(random_string(length=70), "utf-8")
            else:
                doc_body["sg_new_update"] = random_string(length=70)
            return doc_body
        for doc in sg_docs:
            sg_client.update_doc(url=sg_url, db=sg_db, doc_id=doc["id"], number_updates=number_of_updates, auth=session, channels=channels, property_updater=property_updater)


def update_larger_doc(replication_type, cbl_db, db, sg_client, sg_docs, sg_url, sg_db, number_of_updates, session, channels):
    if replication_type == "push":
        doc_ids = db.getDocIds(cbl_db)
        cbl_db_docs = db.getDocuments(cbl_db, doc_ids)
        for doc_id, doc_body in cbl_db_docs.items():
            doc_body["new-1"] = random_string(length=100)
            doc_body["new-2"] = random_string(length=100)
            doc_body["new-3"] = random_string(length=100)
            db.updateDocument(database=cbl_db, data=doc_body, doc_id=doc_id)
    else:
        for doc in sg_docs:
            sg_client.update_doc(url=sg_url, db=sg_db, doc_id=doc["id"], number_updates=number_of_updates, auth=session, channels=channels, property_updater=property_updater)


def property_updater(doc_body):
    doc_body["sg_new_update1"] = random_string(length=100)
    doc_body["sg_new_update2"] = random_string(length=100)
    doc_body["sg_new_update3"] = random_string(length=100)
    return doc_body


def compare_docs(cbl_db, db, sg_docs):
    doc_ids = db.getDocIds(cbl_db)
    cbl_db_docs = db.getDocuments(cbl_db, doc_ids)
    # for sg_doc in zip(sg_docs):
    for sg_doc in sg_docs:
        del sg_doc["doc"]["_rev"]
        key = sg_doc["doc"]["_id"]
        del sg_doc["doc"]["_id"]
        print "sg doc is ", sg_doc["doc"]
        print "cbl doc is ", cbl_db_docs[key]
        assert deep_dict_compare(sg_doc["doc"], cbl_db_docs[key]), "mismatch in the dictionary"


def compare_generic_types(object1, object2):
    if isinstance(object1, str) and isinstance(object2, str):
        return object1 == object2
    elif isinstance(object1, unicode) and isinstance(object2, unicode):
        return object1 == object2
    elif isinstance(object1, bool) and isinstance(object2, bool):
        return object1 == object2
    elif isinstance(object1, int) and isinstance(object2, int):
        return object1 == object2
    elif isinstance(object1, float) and isinstance(object2, float):
        return object1 == object2
    elif isinstance(object1, float) and isinstance(object2, int):
        return object1 == float(object2)
    elif isinstance(object1, int) and isinstance(object2, float):
        return object1 == int(float(object2))

    return True


def deep_list_compare(object1, object2):
    retval = True
    count = len(object1)
    object1 = sorted(object1)
    object2 = sorted(object2)
    for x in range(count):
        if isinstance(object1[x], dict) and isinstance(object2[x], dict):
            retval = deep_dict_compare(object1[x], object2[x])
            if retval is False:
                log_info("Unable to match {} element in dict {} and {}".format(object1, object2))
                return False
        elif isinstance(object1[x], list) and isinstance(object2[x], list):
            retval = deep_list_compare(object1[x], object2[x])
            if retval is False:
                log_info("Unable to match {} element in list {} and {}".format(object1[x], object2[x]))
                return False
        else:
            retval = compare_generic_types(object1[x], object2[x])
            if retval is False:
                log_info("Unable to match objects in generic {} and {}".format(object1[x], object2[x]))
                return False

    return retval


def deep_dict_compare(object1, object2):
    retval = True
    if len(object1) != len(object2):
        log_info("lengths of sgw object and cbl object are different {} --- {}".format(len(object1), len(object2)))
        return False

    for k in object1.iterkeys():
        obj1 = object1[k]
        obj2 = object2[k]
        if isinstance(obj1, list) and isinstance(obj2, list):
            retval = deep_list_compare(obj1, obj2)
            if retval is False:
                log_info("mismatch between sgw: {} and cbl lists :{}".format(obj1, obj2))
                return False

        elif isinstance(obj1, dict) and isinstance(obj2, dict):
            retval = deep_dict_compare(obj1, obj2)
            if retval is False:
                log_info("mismatch between sgw: {} and cbl dict :{}".format(obj1, obj2))
                return False
        else:
            retval = compare_generic_types(obj1, obj2)
            if retval is False:
                log_info("mistmatch {} and {}".format(obj1, obj2))
                return False

    return retval


def get_net_stats(sg_client, sg_admin_url):
    expvars = sg_client.get_expvars(url=sg_admin_url)
    doc_reads_bytes = expvars['syncgateway']['per_db']['db']['database']['doc_reads_bytes_blip']
    doc_writes_bytes = expvars['syncgateway']['per_db']['db']['database']['doc_writes_bytes_blip']
    return doc_reads_bytes, doc_writes_bytes


def verify_delta_stats_counts(sg_client, sg_admin_url, replication_type, sg_db, num_of_docs):
    expvars = sg_client.get_expvars(url=sg_admin_url)
    if replication_type == "push":
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['delta_push_doc_count'] == num_of_docs, "delta push replication count is not right"
        # assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['deltas_requested'] == num_of_docs * 3,"delta requested is not equal to 3 times  of number of docs"
        # assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['deltas_sent'] == num_of_docs * 3,"delta sent is not equal to 3 times  of number of docs"
    else:
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['delta_pull_replication_count'] == 1, "delta pull replication count is not right"
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['deltas_requested'] == num_of_docs, "delta pull requested is not equal to number of docs"
        assert expvars['syncgateway']['per_db'][sg_db]['delta_sync']['deltas_sent'] == num_of_docs, "delta pull sent is not equal to number of docs"


def enable_delta_sync(c, sg_config, cluster_config, mode, delta_sync_enabled):
    temp_cluster_config = copy_to_temp_conf(cluster_config, mode)
    persist_cluster_config_environment_prop(temp_cluster_config, 'delta_sync_enabled', delta_sync_enabled)
    status = c.sync_gateways[0].restart(config=sg_config, cluster_config=temp_cluster_config)
    assert status == 0, "Sync_gateway did not start"
    time.sleep(10)
