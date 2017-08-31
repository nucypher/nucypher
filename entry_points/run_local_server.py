from nkms.network.server import NuCypherDHTServer
import asyncio


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    loop.set_debug(True)
    server = NuCypherDHTServer()
    server.listen(8468)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    loop.close()