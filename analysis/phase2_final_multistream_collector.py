import paramiko
import json
import os
import time
from datetime import datetime

# ==========================
# Jump Host Config
# ==========================
JUMP_HOST = "worker02.air.nvidia.com"
JUMP_USER = "ubuntu"
JUMP_PORT = 23430
JUMP_KEY_PATH = r"C:\Users\prave\.ssh\id_ed25519"

USERNAME = "ubuntu"
PASSWORD = "nvidia"

# ==========================
# Test Configuration
# ==========================
# Replace with your actual IPs from NVIDIA Air topology
TCP_INTRA = {"client": "192.168.200.15", "server": "192.168.200.17"}
TCP_INTER = {"client": "192.168.200.16", "server": "192.168.200.21"}
UDP_INTER = {"client": "192.168.200.16", "server": "192.168.200.21"}

STREAMS = [1, 2, 4, 8, 16, 32]

# ==========================
# Helper Function: SSH via Jump Host
# ==========================
def run_cmd_via_jump(target_ip, cmd):
    jump = paramiko.SSHClient()
    jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pkey = paramiko.Ed25519Key.from_private_key_file(JUMP_KEY_PATH)
    jump.connect(JUMP_HOST, port=JUMP_PORT, username=JUMP_USER, pkey=pkey)

    transport = jump.get_transport()
    dest_addr = (target_ip, 22)
    local_addr = (JUMP_HOST, 22)
    channel = transport.open_channel("direct-tcpip", dest_addr, local_addr)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(target_ip, username=USERNAME, password=PASSWORD, sock=channel)

    stdin, stdout, stderr = ssh.exec_command(cmd)
    output = stdout.read().decode()
    ssh.close()
    jump.close()
    return output


# ==========================
# Function to Run iperf3 and Save JSON
# ==========================
def run_iperf_test(client_ip, server_ip, protocol, streams, folder, label):
    port = 5000 + streams

    print(f"\n▶ Running {label} | Protocol={protocol} | Streams={streams}")

    # Start iperf3 server
    run_cmd_via_jump(server_ip, f"pkill iperf3; nohup iperf3 -s -p {port} -D >/dev/null 2>&1 &")
    time.sleep(2)

    if protocol == "UDP":
        cmd = f"iperf3 -c {server_ip} -p {port} -u -b 100M -P {streams} -t 30 -J"
    else:
        cmd = f"iperf3 -c {server_ip} -p {port} -P {streams} -t 30 -J"

    output = run_cmd_via_jump(client_ip, cmd)

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        print("❌ JSON parse failed, skipping.")
        return

    data["meta_info"] = {
        "protocol": protocol,
        "streams": streams,
        "client": client_ip,
        "server": server_ip,
        "test_name": label,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    os.makedirs(folder, exist_ok=True)
    filename = os.path.join(folder, f"iperf_{label}_P{streams}.json")
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

    print(f"✅ Saved → {filename}")


# ==========================
# MAIN LOGIC
# ==========================
if __name__ == "__main__":
    print("\n🚀 Starting multi-stream tests for TCP intra, TCP inter, and UDP inter...\n")

    # Base folder
    base_dir = "data_results"
    tcp_intra_dir = os.path.join(base_dir, "tcp_intra_leaf")
    tcp_inter_dir = os.path.join(base_dir, "tcp_inter_leaf")
    udp_inter_dir = os.path.join(base_dir, "udp_inter_leaf")

    for streams in STREAMS:
        # TCP INTRA
        run_iperf_test(
            TCP_INTRA["client"], TCP_INTRA["server"],
            protocol="TCP", streams=streams,
            folder=tcp_intra_dir, label="tcp_intra"
        )

        # TCP INTER
        run_iperf_test(
            TCP_INTER["client"], TCP_INTER["server"],
            protocol="TCP", streams=streams,
            folder=tcp_inter_dir, label="tcp_inter"
        )

        # UDP INTER
        run_iperf_test(
            UDP_INTER["client"], UDP_INTER["server"],
            protocol="UDP", streams=streams,
            folder=udp_inter_dir, label="udp_inter"
        )

    print("\n🎯 All test categories completed successfully!")
    print(f"Results organized under → {base_dir}/\n")
