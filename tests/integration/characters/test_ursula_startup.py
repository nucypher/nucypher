def test_new_ursula_announces_herself(lonely_ursula_maker):
    ursula_in_a_house, ursula_with_a_mouse = lonely_ursula_maker(quantity=2, domain="useless_domain")

    # Neither Ursula knows about the other.
    assert ursula_with_a_mouse not in ursula_in_a_house.known_nodes
    assert ursula_in_a_house not in ursula_with_a_mouse.known_nodes

    ursula_in_a_house.remember_node(ursula_with_a_mouse)

    # OK, now, ursula_in_a_house knows about ursula_with_a_mouse, but not vice-versa.
    assert ursula_with_a_mouse in ursula_in_a_house.known_nodes
    assert ursula_in_a_house not in ursula_with_a_mouse.known_nodes

    # But as ursula_in_a_house learns, she'll announce herself to ursula_with_a_mouse.
    ursula_in_a_house.learn_from_teacher_node()

    assert ursula_with_a_mouse in ursula_in_a_house.known_nodes
    assert ursula_in_a_house in ursula_with_a_mouse.known_nodes


def test_node_deployer(blockchain_ursulas):
    for ursula in blockchain_ursulas:
        deployer = ursula.get_deployer()
        assert deployer.options['https_port'] == ursula.rest_information()[0].port
        assert deployer.application == ursula.rest_app
