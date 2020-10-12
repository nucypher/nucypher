import asyncio
import time
from twisted.internet.defer import Deferred
from web3 import WebsocketProvider
from websockets.protocol import WebSocketCommonProtocol

from nucypher.blockchain.eth.interfaces import BlockchainInterface
from web3 import Web3
from twisted.internet import reactor


def test_whatever():

    def get_version(w3: Web3):
        for i in range(100):
            print(f"{w3.clientVersion}")


    provider = WebsocketProvider('wss://<ACTUAL INFURA ENDPOINT>')
    w3 = Web3(provider=provider)

    reactor.callInThread(get_version, w3)
    reactor.callInThread(get_version, w3)


    #####

    #
    # blockchain = BlockchainInterface(provider_uri="ws://nowhere", poa=True)
    # u0, u1 = blockchain_ursulas[0], blockchain_ursulas[1]
    # s0 = u0._staker_is_really_staking(test_registry)
    # # blockchain.connect()
    # mock_staking_agent.blockchain = blockchain
    # assert False


#
# def test_backpressure_on_web3_activity(blockchain_ursulas, test_registry, mock_staking_agent):
#     mock_staking_agent.get_locked_tokens(staker_address="0xE57bFE9F44b819898F47BF37E5AF72a0783e1141", periods=0)
#     ################
#
#     u0, u1 = blockchain_ursulas[0], blockchain_ursulas[1]
#     u0.staking_agent.blockchain._provider = WebsocketProvider
#
#     asyncio_event_loop = asyncio.events.get_event_loop()
#
#     async def spinner(*args, **kwargs):
#         for _i in range(100):  # In case everything else hangs, we'll bail after 100 iterations.
#             time.sleep(.001)
#         asyncio_event_loop.stop()
#
#     wscp = WebSocketCommonProtocol()
#     wscp.transfer_data_task = spinner()
#
#     s0 = u0._staker_is_really_staking(test_registry)
#     s1 = u1._staker_is_really_staking(test_registry)
#
#     asyncio_event_loop.run_forever()
#
#     problems = []
#
#     def _handle_failure(failure):
#         problems.append(failure.getErrorMessage())
#         asyncio_event_loop.stop()
#
#     def llama(result):
#         assert result  # Not much of interest that we can really assert here.
#
#     def wrap_websocket_call_to_simulate_conditions_in_the_codebase(coro_callable):
#         recv_coro = coro_callable()
#         _future = asyncio.ensure_future(recv_coro)
#         d = Deferred.fromFuture(_future)
#         d.addCallback(llama)
#         d.addErrback(_handle_failure)
#         return d
#
#     # Not a problem.
#     d1 = wrap_websocket_call_to_simulate_conditions_in_the_codebase(wscp.recv)
#
#     # ...but since it hasn't returned when we call this one, we'll get an error, which will be added to `problems`
#     d2 = wrap_websocket_call_to_simulate_conditions_in_the_codebase(wscp.recv)
#
#     asyncio_event_loop.run_forever()
#
#     assert len(problems) == 1
#     assert problems[0] == 'cannot call recv while another coroutine is already waiting for the next message'
