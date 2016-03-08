*** Settings ***
Resource    resources/common.robot

Library     Process
Library     OperatingSystem
Library     ${Libraries}/ClusterKeywords.py
Library     TestUsersChannels.py
Library     TestSync.py
Library     TestBulkGetCompression.py
Library     TestContinuous.py
Library     TestBucketShadow.py


Test Setup      Setup
Test Teardown   Teardown

*** Variables ***
${SERVER_VERSION}           4.1.0
${SYNC_GATEWAY_VERSION}     1.2.0-79
${CLUSTER_CONFIG}           ${CLUSTER_CONFIGS}/2sg_1cbs
${SYNC_GATEWAY_CONFIG}      ${SYNC_GATEWAY_CONFIGS}/sync_gateway_default_functional_tests_cc.json

*** Test Cases ***
# Cluster has been setup

# TestBucketShadow
test bucket shadow multiple sync gateways
    test bucket shadow multiple sync gateways


*** Keywords ***
Setup
    Log To Console      Setting up ...
    Set Environment Variable    CLUSTER_CONFIG    ${cluster_config}
    #Provision Cluster   ${SERVER_VERSION}   ${SYNC_GATEWAY_VERSION}    ${SYNC_GATEWAY_CONFIG}

Teardown
    Log To Console      Tearing down ...