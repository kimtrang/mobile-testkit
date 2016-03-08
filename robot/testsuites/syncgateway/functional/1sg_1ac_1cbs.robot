*** Settings ***
Resource    resources/common.robot

Library     Process
Library     OperatingSystem
Library     ${Libraries}/ClusterKeywords.py
Library     TestUsersChannels.py


Test Setup      Setup
Test Teardown   Teardown

*** Variables ***
${SERVER_VERSION}           4.1.0
${SYNC_GATEWAY_VERSION}     1.2.0-79
${CLUSTER_CONFIG}           ${CLUSTER_CONFIGS}/1sg_1ac_1cbs

*** Test Cases ***
# Cluster has been setup

# TestContinuous
test continuous changes parametrized 1 user 5000 docs 1 revision
    test continuous changes parametrized    ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_di.json  ${1}  ${5000}  ${1}

test continuous changes parametrized 50 users 5000 docs 1 revision
    test continuous changes parametrized    ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_di.json  ${50}  ${5000}  ${1}

test continuous changes parametrized 50 users 5000 10 docs 10 revisions
    test continuous changes parametrized    ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_di.json  ${50}  ${10}  ${10}

test continuous changes parametrized 50 user 50 docs 1000 revisions
    test continuous changes parametrized    ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_di.json  ${50}  ${50}  ${1000}

test continuous changes sanity
    test_continuous_changes_sanity          ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_di.json  ${10}  ${10}

# TestSync (Distributed Index)
test issue 1524
     test issue 1524            ${SYNC_GATEWAY_CONFIGS}/custom_sync/grant_access_one_di.json.json   ${10}

test sync access sanity
    test sync access sanity     ${SYNC_GATEWAY_CONFIGS}/custom_sync/sync_gateway_custom_sync_access_sanity_di.json

test sync channel sanity
    test sync channel sanity    ${SYNC_GATEWAY_CONFIGS}/custom_sync/sync_gateway_custom_sync_channel_sanity_di.json

test sync role sanity
    test sync role sanity       ${SYNC_GATEWAY_CONFIGS}/custom_sync/sync_gateway_custom_sync_role_sanity_di.json

test sync sanity
    test sync sanity            ${SYNC_GATEWAY_CONFIGS}/custom_sync/sync_gateway_custom_sync_one_di.json

test sync sanity backfill
    test sync sanity backfill   ${SYNC_GATEWAY_CONFIGS}/custom_sync/sync_gateway_custom_sync_one_di.json

test sync require roles
    test sync require roles     ${SYNC_GATEWAY_CONFIGS}/custom_sync/sync_gateway_custom_sync_require_roles_di.json

# TestUsersChannels (Distributed Index)
test multiple users multiple channels (distributed index)
    test multiple users multiple channels   ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_di.json

test muliple users single channel (distributed index)
    test muliple users single channel       ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_di.json

test single user multiple channels (distributed index)
    test single user multiple channels      ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_di.json

test single user single channel (distributed index)
    test single user single channel         ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_di.json

*** Keywords ***
Setup
    Log To Console      Setting up ...
    Set Environment Variable    CLUSTER_CONFIG    ${cluster_config}
    #Provision Cluster   ${SERVER_VERSION}   ${SYNC_GATEWAY_VERSION}    ${SYNC_GATEWAY_CONFIG}
    #Install Sync Gateway   ${CLUSTER_CONFIG}    ${SYNC_GATEWAY_VERSION}    ${SYNC_GATEWAY_CONFIG}

Teardown
    Log To Console      Tearing down ...