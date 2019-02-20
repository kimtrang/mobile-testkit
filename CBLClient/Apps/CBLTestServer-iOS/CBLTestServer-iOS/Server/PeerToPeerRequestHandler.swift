//
//  PeerToPeerRequestHandler.swift
//  CBLTestServer-iOS
//
//  Created by Sridevi Saragadam on 7/23/18.
//  Copyright © 2018 Raghu Sarangapani. All rights reserved.
//
import Foundation
import CouchbaseLiteSwift


public class PeerToPeerRequestHandler {
    public static let VOID: String? = nil
    fileprivate var _pushPullReplListener:NSObjectProtocol?
    private func _replicatorBooleanFilterCallback(document: Document, flags: DocumentFlags) -> Bool {
        let key:String = "new_field_1"
        if document.contains(key){
            let value:Bool = document.boolean(forKey: key)
            return value;
        }
        return true
    }

    private func _defaultReplicatorFilterCallback(document: Document, flags: DocumentFlags) -> Bool {
        return true;
    }

    private func _replicatorDeletedFilterCallback(document: Document, documentFlags: DocumentFlags) -> Bool {
        if (documentFlags.rawValue == 1) {
            return false
        }
        return true
    }

    private func _replicatorAccessRevokedCallback(document: Document, documentFlags: DocumentFlags) -> Bool {
        if (documentFlags.rawValue == 2) {
            return false
        }
        return true
    }

    public func handleRequest(method: String, args: Args) throws -> Any? {
        
        switch method {
            
            /////////////////////////////
            // Peer to Peer Apis //
            ////////////////////////////
            
        case "peerToPeer_serverStart":
            let database: Database = args.get(name:"database")!
            let port: Int = args.get(name:"port")!
            let peerToPeerListener: ReplicatorTcpListener = ReplicatorTcpListener(databases: [database], port: UInt32(port))
            peerToPeerListener.start()
            print("Server is getting started")
            return peerToPeerListener
            
        case "peerToPeer_serverStop":
            let peerToPeerListener: ReplicatorTcpListener = args.get(name:"replicatorTcpListener")!
            peerToPeerListener.stop()
            
        case "peerToPeer_configure":
            let host: String = args.get(name:"host")!
            let port: Int = args.get(name:"port")!
            let serverDBName: String = args.get(name:"serverDBName")!
            let database: Database = args.get(name:"database")!
            let continuous: Bool? = args.get(name:"continuous")!
            let replication_type: String? = args.get(name: "replicationType")!
            let documentIDs: [String]? = args.get(name: "documentIDs")
            let endPointType: String = args.get(name: "endPointType")!
            let pull_filter: Bool? = args.get(name: "pull_filter")!
            let push_filter: Bool? = args.get(name: "push_filter")!
            let filter_callback_func: String? = args.get(name: "filter_callback_func")
            var replicatorConfig: ReplicatorConfiguration
            var replicatorType = ReplicatorType.pushAndPull
            
            if let type = replication_type {
                if type == "push" {
                    replicatorType = .push
                } else if type == "pull" {
                    replicatorType = .pull
                } else {
                    replicatorType = .pushAndPull
                }
            }
            
            let url = URL(string: "ws://\(host):\(port)/\(serverDBName)")!
            if endPointType == "URLEndPoint"{
                let urlEndPoint: URLEndpoint = URLEndpoint(url: url)
                replicatorConfig = ReplicatorConfiguration(database: database, target: urlEndPoint)
            }
            else{
                let endpoint = MessageEndpoint(uid: url.absoluteString, target: url, protocolType: ProtocolType.byteStream, delegate: self)
                replicatorConfig = ReplicatorConfiguration(database: database, target: endpoint)
            }
            
            if continuous != nil {
                replicatorConfig.continuous = continuous!
            } else {
                replicatorConfig.continuous = false
            }
            if documentIDs != nil {
                replicatorConfig.documentIDs = documentIDs
            }
            if pull_filter != false {
                if filter_callback_func == "boolean" {
                    replicatorConfig.pullFilter = _replicatorBooleanFilterCallback;
                } else if filter_callback_func == "deleted" {
                    replicatorConfig.pullFilter = _replicatorDeletedFilterCallback;
                } else if filter_callback_func == "access_revoked" {
                    replicatorConfig.pullFilter = _replicatorAccessRevokedCallback;
                } else {
                    replicatorConfig.pullFilter = _defaultReplicatorFilterCallback;
                }
            }
            if push_filter != false {
                if filter_callback_func == "boolean" {
                    replicatorConfig.pushFilter = _replicatorBooleanFilterCallback;
                } else if filter_callback_func == "deleted" {
                    replicatorConfig.pushFilter = _replicatorDeletedFilterCallback;
                } else if filter_callback_func == "access_revoked" {
                    replicatorConfig.pushFilter = _replicatorAccessRevokedCallback;
                } else {
                    replicatorConfig.pushFilter = _defaultReplicatorFilterCallback;
                }
            }
            replicatorConfig.replicatorType = replicatorType
            let replicator: Replicator = Replicator(config: replicatorConfig)
            return replicator

        case "peerToPeer_clientStart":
            let replicator: Replicator = args.get(name:"replicator")!
            replicator.start()
            print("Replicator has started")
            
        case "peerToPeer_addReplicatorEventChangeListener":
            let replication_obj: Replicator = args.get(name: "replicator")!
            let changeListener = MyDocumentReplicationListener()
            let listenerToken = replication_obj.addDocumentReplicationListener(changeListener.listener)
            changeListener.listenerToken = listenerToken
            return changeListener

        case "peerToPeer_removeReplicatorEventListener":
            let replication_obj: Replicator = args.get(name: "replicator")!
            let changeListener : MyDocumentReplicationListener = (args.get(name: "changeListener"))!
            replication_obj.removeChangeListener(withToken: changeListener.listenerToken!)

        case "peerToPeer_replicatorEventChangesCount":
            let changeListener: MyDocumentReplicationListener = (args.get(name: "changeListener"))!
            return changeListener.getChanges().count

        case "peerToPeer_replicatorEventGetChanges":
            let changeListener: MyDocumentReplicationListener = (args.get(name: "changeListener"))!
            let changes: [DocumentReplication] = changeListener.getChanges()
            var event_list: [String] = []
            for change in changes {
                for document in change.documents {
                    let doc_event:String = "doc_id: " + document.id
                    let error:String = ", error_code: " + document.error.debugDescription + ", error_domain: nil"
                    let flags:String = ", flags: " + document.flags.rawValue.description
                    let push:String = ", push: " + change.isPush.description
                    event_list.append(doc_event + error + push + flags)
                }
            }
            return event_list

        default:
            throw RequestHandlerError.MethodNotFound(method)
        }
        return PeerToPeerRequestHandler.VOID
    }
}

extension PeerToPeerRequestHandler: MessageEndpointDelegate {
    public func createConnection(endpoint: MessageEndpoint) -> MessageEndpointConnection {
        let url = endpoint.target as! URL
        return ReplicatorTcpClientConnection.init(url: url)
    }
}
