[ping_probe://<name>]
count = (Default: 4)
index = Destination index. Leave unset to route to the admin default; align the netkit_index macro on the search head to match. (Default: default)
interval = (Default: 60)
targets = Hostname, IPv4, or IPv6 host:port, comma-separated. IPv6 literals go without brackets; the last colon separates the port. e.g. 1.1.1.1:443,example.com:8089,2606:4700:4700::1111:443
timeout_ms = (Default: 2000)
python.required = {3.7|3.9|3.13}
* For Python scripts only, selects which Python version to use.
* Set to "3.9" to use the Python 3.9 version.
* Set to "3.13" to use the Python 3.13 version.
* Optional.
* Default: not set

[speedtest_probe://<name>]
download_mb = Bytes downloaded per run when the profile is Custom (1-500 MB). (Default: 25)
index = Destination index. Leave unset to route to the admin default; align the netkit_index macro on the search head to match. (Default: default)
interval = Seconds between runs. Minimum 300; the High bandwidth and Custom profiles require at least 900. (Default: 1800)
profile = Transfer sizes per run. Larger sizes measure fast links more accurately but use more data per run. (Default: standard)
upload_mb = Bytes uploaded per run when the profile is Custom (1-100 MB). (Default: 5)
python.required = {3.7|3.9|3.13}
* For Python scripts only, selects which Python version to use.
* Set to "3.9" to use the Python 3.9 version.
* Set to "3.13" to use the Python 3.13 version.
* Optional.
* Default: not set
