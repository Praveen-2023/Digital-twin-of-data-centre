import paramiko, json, os, time
from datetime import datetime

# -----------------------------
# Jump Host / Credentials
# -----------------------------
JUMP_HOST = "worker02.air.nvidia.com"
JUMP_USER = "ubuntu"
JUMP_PORT = 23430
JUMP_KEY_PATH = r"C:\Users\prave\.ssh\id_ed25519"

USERNAME = "ubuntu"
PASSWORD = "nvidia"

# -----------------------------
# Network Topology (Edit IPs if needed)
# -----------------------------
TCP_INTRA = {"client": "192.168.200.15", "server": "192.168.200.17"}
TCP_INTER = {"client": "192.168.200.16", "server": "192.168.200.21"}
UDP_INTER = {"client": "192.168.200.16", "server": "192.168.200.21"}

STREAMS = [1, 2, 4, 8, 16, 32]
FAULT_NODE = "192.168.200.17"       # Node where we simulate failure
FAULT_INTERFACE = "eth1"            # Interface to disable for fault simulation
DURATION = 120                      # Test duration in seconds

# -----------------------------
# Helper: SSH via Jump Host
# -----------------------------
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

# -----------------------------
# Function to Run iperf3 and Save JSON
# -----------------------------
def run_iperf_test(client, server, proto, streams, phase, folder, label):
    port = 5200 + streams
    os.makedirs(folder, exist_ok=True)
    print(f"▶ {label} | {proto} | {phase} | P={streams}")

    # Start iperf3 server
    run_cmd_via_jump(server, f"pkill iperf3; nohup iperf3 -s -p {port} -D >/dev/null 2>&1 &")
    time.sleep(2)

    if proto == "UDP":
        cmd = f"iperf3 -c {server} -p {port} -u -b 100M -P {streams} -t {DURATION} -J"
    else:
        cmd = f"iperf3 -c {server} -p {port} -P {streams} -t {DURATION} -J"

    output = run_cmd_via_jump(client, cmd)
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        print("❌ JSON parse failed, skipping.")
        return

    data["meta_info"] = {
        "phase": phase,
        "protocol": proto,
        "streams": streams,
        "duration_sec": DURATION,
        "client": client,
        "server": server,
        "test_name": label,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    filename = os.path.join(folder, f"iperf_{label}_{proto}_P{streams}_{phase}.json")
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)
    print(f"✅ Saved → {filename}")

# -----------------------------
# Fault Simulation Phase
# -----------------------------
def fault_phase(label, pair, proto, base_dir):
    folder = os.path.join(base_dir, f"{proto.lower()}_{label}")

    # --- 1. Before Fault ---
    print(f"\n🟢 Running {label} BEFORE fault...")
    for s in STREAMS:
        run_iperf_test(pair["client"], pair["server"], proto, s, "before", folder, label)

    # --- 2. Simulate Fault ---
    print(f"\n⚠️ Disabling link {FAULT_INTERFACE} on {FAULT_NODE}...\n")
    run_cmd_via_jump(FAULT_NODE, f"sudo ip link set {FAULT_INTERFACE} down")
    time.sleep(5)

    print(f"🟠 Running {label} DURING fault...")
    for s in STREAMS:
        run_iperf_test(pair["client"], pair["server"], proto, s, "during", folder, label)

    # --- 3. Recover Network ---
    print(f"\n🔁 Restoring link {FAULT_INTERFACE} on {FAULT_NODE}...\n")
    run_cmd_via_jump(FAULT_NODE, f"sudo ip link set {FAULT_INTERFACE} up")
    time.sleep(10)

    print(f"🔵 Running {label} AFTER recovery...")
    for s in STREAMS:
        run_iperf_test(pair["client"], pair["server"], proto, s, "after", folder, label)

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    print("\n🚀 Starting 120-second Fault Tolerance Tests...\n")
    base_dir = "fault_tolerance_results_120s"
    os.makedirs(base_dir, exist_ok=True)

    fault_phase("tcp_intra_leaf", TCP_INTRA, "TCP", base_dir)
    fault_phase("tcp_inter_leaf", TCP_INTER, "TCP", base_dir)
    fault_phase("udp_inter_leaf", UDP_INTER, "UDP", base_dir)

    print("\n🎯 All 120s fault-tolerance tests complete! Results in 'fault_tolerance_results_120s/'\n")
