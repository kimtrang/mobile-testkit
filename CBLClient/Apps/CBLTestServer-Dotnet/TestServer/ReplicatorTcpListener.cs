using Couchbase.Lite.P2P;
using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;

namespace Couchbase.Lite.Testing
{
    public sealed class ReplicatorTcpListener
    {
        private TcpClient _connectedTcpClient;
        private TcpListener _listener;
        private MessageEndpointListener _endpointListener;
        private bool _opened;

        /// <summary>
        /// Constructs a new replicator Passive Peer Tcp listener
        /// </summary>
        /// <param name="endpointListener">used to accept any incoming peer tcp client connection</param>
        public ReplicatorTcpListener(MessageEndpointListener endpointListener)
        {
            _endpointListener = endpointListener;
        }

        /// <summary>
        /// Tcp listener starts to listen for incoming and accept tcp connection(s)
        /// </summary>
        public void Start()
        {
            if (_listener == null)
            {
                try
                {
                    _listener = new TcpListener(IPAddress.Any, TcpMessageEndpointConnection.Port);
                    _listener.Start();
                    _opened = true;
                    AcceptLoop();

                }
                catch (Exception)
                {
                    //placerholder for customized logging or error handling
                }
            }

        }

        /// <summary>
        /// Stop Tcp listener to listen for incoming tcp connection(s)
        /// </summary>
        public bool Stop()
        {

            if (_listener != null)
            {
                _opened = false;
                _listener.Stop();
                _listener = null;
                _endpointListener = null;
                return true;
            }

            return false;
        }

        private async Task AcceptLoop()
        {
            while (_opened)
            {
                _connectedTcpClient = await _listener?.AcceptTcpClientAsync();
                var socketConnection = new TcpMessageEndpointConnection(_connectedTcpClient);
                _endpointListener.Accept(socketConnection);
            }
        }
    }
}