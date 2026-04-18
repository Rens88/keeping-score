$HostAddress = if ($env:STREAMLIT_SERVER_ADDRESS) { $env:STREAMLIT_SERVER_ADDRESS } else { "0.0.0.0" }
$PortNumber = if ($env:STREAMLIT_SERVER_PORT) { $env:STREAMLIT_SERVER_PORT } else { "8501" }

streamlit run app.py --server.address $HostAddress --server.port $PortNumber
