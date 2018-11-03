
# Set Default Curve #
#####################

from umbral.config import set_default_curve
set_default_curve()

#####################


# Report to Sentry #
####################

import sentry_sdk
sentry_sdk.init("https://d8af7c4d692e4692a455328a280d845e@sentry.io/1310685")

####################
