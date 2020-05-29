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

import io


class MockStdinWrapper:

    def __init__(self):
        self.mock_stdin = MockStdin()
        self.mock_getpass = MockGetpass()

    def line(self, s):
        self.mock_stdin.line(s)

    def password(self, s, confirm=False):
        self.mock_getpass.line(s)
        if confirm:
            self.mock_getpass.line(s)

    def empty(self):
        return self.mock_stdin.empty() and self.mock_getpass.empty()


class MockStdinBase:

    def __init__(self):
        self.stream = io.StringIO()
        self.lines = 0

    def line(self, s):
        pos = self.stream.tell() # preserve the current read pointer
        self.stream.seek(0, io.SEEK_END)
        self.stream.write(s + '\n')
        self.stream.seek(pos)
        self.lines += 1

    def _readline(self):
        assert self.lines > 0, "Stdin was queried, but the list of mock inputs is empty"
        self.lines -= 1
        return self.stream.readline()

    def empty(self):
        return self.lines == 0


class MockGetpass(MockStdinBase):
    """
    Mocks `getpass.getpass()`
    """

    def __call__(self, prompt):
        print(prompt, end='')
        s = self._readline()
        return s[:-1] # remove the final line break


class MockStdin(MockStdinBase):
    """
    Mocks `sys.stdin`
    """
    def readline(self):
        return self._readline()
