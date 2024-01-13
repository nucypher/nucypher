from nucypher.blockchain.eth import domains

TEACHER_NODES = {
    domains.MAINNET: (
        "https://closest-seed.nucypher.network:9151",
        "https://seeds.nucypher.network:9151",
        "https://mainnet.nucypher.network:9151",
    ),
    domains.LYNX: ("https://lynx.nucypher.network:9151",),
    domains.TAPIR: ("https://tapir.nucypher.network:9151",),
}
