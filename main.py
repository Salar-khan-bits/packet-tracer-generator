
from pathlib import Path
from pkt_core import Lab


def generate_network():
    # Project paths
    project_dir = Path(__file__).resolve().parent
    output_dir = project_dir / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "first_network.pkt"

    # Create Packet Tracer lab
    lab = Lab()

    # Remove default seed devices
    lab.prune_seed_devices()

    # ---------------------------------
    # 1. Create network devices
    # ---------------------------------

    router = lab.add_device(
        model="2911",
        name="Router0",
        x=350,
        y=100,
        ios_config=[
            "enable",
            "configure terminal",
            "hostname Router0",
            "interface GigabitEthernet0/0",
            "ip address 192.168.10.1 255.255.255.0",
            "no shutdown",
            "exit",
            "end",
        ],
    )

    switch = lab.add_device(
        model="2960-24TT",
        name="Switch0",
        x=350,
        y=250,
    )

    # ---------------------------------
    # 2. Create end devices
    # ---------------------------------

    pc1 = lab.add_device(
        model="PC-PT",
        name="PC1",
        x=150,
        y=400,
        pc_ip=[
            "192.168.10.11",
            "255.255.255.0",
            "192.168.10.1",
        ],
    )

    pc2 = lab.add_device(
        model="PC-PT",
        name="PC2",
        x=350,
        y=400,
        pc_ip=[
            "192.168.10.12",
            "255.255.255.0",
            "192.168.10.1",
        ],
    )

    server = lab.add_device(
        model="Server-PT",
        name="Server0",
        x=550,
        y=400,
        pc_ip=[
            "192.168.10.10",
            "255.255.255.0",
            "192.168.10.1",
        ],
    )

    # ---------------------------------
    # 3. Connect devices
    # ---------------------------------

    # Router to switch
    lab.link(
        router,
        "GigabitEthernet0/0",
        switch,
        "GigabitEthernet0/1",
        kind="copper",
    )

    # PC1 to switch
    lab.link(
        pc1,
        "FastEthernet0",
        switch,
        "FastEthernet0/1",
        kind="copper",
    )

    # PC2 to switch
    lab.link(
        pc2,
        "FastEthernet0",
        switch,
        "FastEthernet0/2",
        kind="copper",
    )

    # Server to switch
    lab.link(
        server,
        "FastEthernet0",
        switch,
        "FastEthernet0/3",
        kind="copper",
    )

    # ---------------------------------
    # 4. Export Packet Tracer file
    # ---------------------------------

    lab.save(str(output_file))

    print("\nNetwork generated successfully!")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    try:
        generate_network()
    except Exception as error:
        print("\nNetwork generation failed!")
        print(f"Error: {error}")
        raise
