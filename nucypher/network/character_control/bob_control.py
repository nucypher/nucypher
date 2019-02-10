from flask import Flask, request, Response

def make_bob_control(drone_bob: 'Bob'):
    bob_control = Flask('bob-control')

    @bob_control.route('/join_policy', methods=['POST'])
    def join_policy():
        try:
            pass
        except KeyError as e:
            return Response(e, status=500)


    @bob_control.route('/retrieve', methods=['POST'])
    def retrieve():
        try:
            pass
        except KeyError as e:
            return Response(e, status=500)

    return bob_control
