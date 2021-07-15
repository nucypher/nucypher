"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from base64 import b64decode

import pytest

from nucypher.crypto.umbral_adapter import PublicKey


@pytest.fixture(scope='session')
def random_federated_treasure_map_data():
    #
    # These values were obtained from running the federated heartbeat demo and printing the relevant values.
    #
    random_bob_encrypting_key = PublicKey.from_bytes(
        bytes.fromhex("026d1f4ce5b2474e0dae499d6737a8d987ed3c9ab1a55e00f57ad2d8e81fe9e9ac"))
    random_treasure_map_id = "cc1c29dd2305483cc838cbcc5ecb5ef6edfd69ecadb0aa52b6b084b630989187"  # federated is 32 bytes
    random_treasure_map = b64decode("VE0AAZ3jsXPynMD9dm+Fjwi49bxkOzUjwsNI0Y0p8bGB9F60OXGmJqibK0Ki4FSWti2Y"
                                    "vUDuxMBrx8BidK00ITuDVoz037tyvCyOL+5Wcy5/LRD8AAAIgQOfxCS16Gu9aw0iy/G9"
                                    "9JUW/hfj6Mt3lM7+hIrLASpMZgJO1o5GbBumlzv0w90HAwXGNrJkhbTgUpRgO0vsGqtr"
                                    "OtuWe0lUNvLqPwvLbq1r5FmBD6FmvlfsiKI3aoKUgChEAlXU5d/KqJjvMHIih/yQNpZv"
                                    "5RFBK52YiOEAb8EO4FqyAAAH+tzB7Fk7m8iVP/UILgco37l8EF2edLJyZloxggpe9cN7"
                                    "fs5hHwAxTgRBCI3fZCyKxkZxVyFlPnRuih1A6dZJLOqeQGtDCsPDA/3wi1ND1swM31ti"
                                    "2PopqoLTmhqWJvu+dqTqeqOAMXehbx/e5gpYEeyIFbt5dQyp7MLGHlGzvvbhh7SLqDN7"
                                    "vGY4l9lnwNDfyVMZ2t0Q43oKYvv9YTSDkxJqeooTT21vcpLB3DMcjs2Geq3Zapcn2bfp"
                                    "QoRh0ZyAjKTR650PDOA2DgwkuWfkTWJk8E9a1EVnV5zeWNQB3nH5jfP5Tq/tXVs/4I8A"
                                    "nvALP74PjDYmzwTkPWsZ4sKMe/3vrvu1cZMblv/3c006nhWTqGlYKP52d8mGzgORWCqA"
                                    "Pn+to2xEIZZETUl4uWgJfMRlih0/kq1T6aHoIyr16hQKv9uJKnIbsdBE/D4eQUEvAUk/"
                                    "YVQhoETgznQK04vMgLHErhiT/JquA2DZNKg7/Nw8L4Z49anwoYPxqbP9djcOnxzy2Iupv"
                                    "HZrMX5D3tZHBszSwxQ7NiZRa38Hn/ed1Jodgv7j2nhRQVc+HZSJmj522FISk3wKMgNaHq"
                                    "RbtmNot/4bRCARaDB1spOvnxqemq+RfsmCUJcsTjyjEfwHm74UD+G4Hv/3h9DEmWPnJ23"
                                    "5q0x2LoodOnMJ3QjjN5qZoQuU3vk8f6zdKNkXWqPrnRPx89okX/N7sW6wk2lJESRO53I2"
                                    "+IirUIlVYfWmUuTvleeH15p+kjIuzaO+xGVHuOT/r6onc5+CJDUYih5NuAzzoAcThi8l/"
                                    "6ZLTDi+uIj9hcqylBU1lf/ZB3TY7h03eMwEimflpti/DBqArZ1i81l9grTU+Rzx86p9rk"
                                    "VaS+B7v3oft7Zm/UTvLk7BZIsjrMmAhLTJKUNY2svzA2dlXlEDmlmAJzrz/gsWph1u7ds"
                                    "WpN3xQytHwRpCgfin4Ndzag9rZg2Gpy0IqS3x/csxp42HTHoeJ6xAp6UX5PEfY6MrWTqf"
                                    "jCfLBnhli4+1Jb+kum1o7sD4htKnTezKndZuEIYDmLw3C0uPxDZGpckr05ZGBBDnLi8cp"
                                    "KSs+WUJccdUQazo6JkHKbejCtneTctqjAgKHTXb5ReYqcTiQ4Z0OXFUNzQvYcXrOqhb3r"
                                    "OqZIDtnqIkjkUqmT1DBOjGazuLCX4rkbwCx5h+D2/+L66KShwh5oVPIkKOHf/DvGVq1E/"
                                    "skIFPWtNOyBCwZS1OWo2zOEi19t/TP7aCn/HjLrZdlOf5X+6Yoh9VytCgnX+Pc4cvzMhE"
                                    "9o4TurtPxmOfQs5y7EhFY+3leF+x0RHaOLPNEtr1cjNpLguvm5GGM0rcFkpZh1Zr8UBcf"
                                    "poLCWvupdvkzCyS78gda637+57M6ZNiaE9oNuvXaiG2MXUzyBx9DBdXKieJsKjhZZ9VTP"
                                    "7ceJuM70USFTV3K2yRCsHpoxX7qql9k1+ZChFQNP0LYHuo7FAMMIq4nu7B2R9yjKDON1Z"
                                    "5JxcsKxZrFR90kH3oogVQP0gegF1qGGdfT87cLZmpFHB1Vuzsu7AcpjRay+nDhi+HdG/+"
                                    "PeeobJwgpA3L5/0JKoB2cpXQY4p2bCzFBInG64Bl6AEQYPEB13u3D7iC1k4j9xxUgRX+t"
                                    "fX0Kp3VojnAaawAc6Et/vJ/13p7DHvPvWXz7A9ZNHoTpZV7rp9ZhZCXrDCfqPc9Q9+Cwa"
                                    "LU8m/9aEz/VKN/TyZdyZJlGBJ7NXCQf0qnZh7rgA0I/lhvJ4SFkLiqA8OuouVGDGgrvm/"
                                    "ySiNcVOlwdXDDqCYn4vNA3PwpDdK6XjA4btlvTK1Xm6cnPMrJ/Yk65qfEnaCGspmSK8pG"
                                    "SIyuvECAktRCg/IETZTqFo43ewt0wWlROR1Veib/+ZbjbPbVmphGSUaLakG+NKEnDdyGZ"
                                    "JJ5ZxGnA6V7P1SwM+1MuNZaovJWbX8Kk1jIg0Y9fCpOcB8nDiwpgcapi5YGS3kgP1Hwny"
                                    "OvAQwYjb6xdYTC8hsLp9gnRFYyDGSyGeCFJ1yxwC6u+o4ex4hetAMl7Ce3sVc66XKVZWf"
                                    "IEjmODRE3ztghuSGRWmVG20wTS4+Iya69WAynWv1DYXfzQ5h/5NK5JjuJftvod8uq5UReo"
                                    "98bH2OIrnTfpGzDDcl48AYzRQJ4/lokBVgWrdKfscv7Z55RVxyjR7eOoXZGzFlmkj7YKG+"
                                    "NJmZsC1Glrtz6sc7xmldEWFfk+Zb2j2HKLzJ99ekqGJpcrQSJAs6nXINplVnI8psrpOG8/"
                                    "cTIqMsliL+i9qZxUX6sl//fj2eR4nzb0W1qItXyS2UOMC1t7MgzICsfn0VWzIT0da4f6za"
                                    "EQEBjtYWEmj7UJTlVm+L+utlMFFtunRD6uCibBVTtqZY5oTN8IUyTYyGV+K7w5jpm1ceUm"
                                    "0kSeqivSArWInnpk7S098lz8DtFsXxJwhsKUXyOjWXAyYOTzIuB8HxvQ92KyPKrD927iZL"
                                    "5q8DYgC8q5fozFbWFJ6Do+6STVtqYtngNCizrIoBg2/OMx0pUUGkH+S9b7wfordn+czd6s"
                                    "t8NoCij4F3nHx8dvA2ZKEoC5YlrEsJBjdKHZwRPtQ6H8bDj2C20K48t4jQ26GPqithBkYE"
                                    "ogU/kE00AE+L0JJQAkgWotyF28V/+awu+rpeuJ4eKzUS0ig0YiLYSfSAsqCARahH25QljG"
                                    "pYabC2hGmPwkD9pGEymtCcFnf47Zhi6v7LkrbatbLk8ebIMm21a6WLy")
    yield random_bob_encrypting_key, random_treasure_map_id, random_treasure_map
