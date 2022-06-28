from nucypher.policy.conditions.base import ReencryptionCondition
from nucypher.policy.conditions.payment import SubscriptionManagerPayment, FreeReencryptions

PAYMENT_METHODS = {
    FreeReencryptions.NAME: FreeReencryptions,
    SubscriptionManagerPayment.NAME: SubscriptionManagerPayment,
}

REENCRYPTION_CONDITIONS = {
    **PAYMENT_METHODS,
}
