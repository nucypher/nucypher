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

import subprocess
import sys
import venv
from pathlib import (
    Path,
)
from tempfile import (
    TemporaryDirectory,
)
from typing import (
    Tuple,
)


def create_venv(parent_path: Path) -> Path:
    if hasattr(sys, 'real_prefix'):
        # python is currently running inside a venv
        # pip_path = Path(sys.executable).parent
        raise RuntimeError("Disable venv and try again.")

    venv_path = parent_path / 'package-smoke-test'
    pip_path = venv_path / 'bin' / 'pip'

    venv.create(venv_path, with_pip=True)
    assert Path.exists(venv_path), f'venv path "{venv_path}" does not exist.'
    assert Path.exists(pip_path), f'pip executable not found at "{pip_path}"'

    subprocess.run([pip_path, 'install', '-U', 'pip', 'setuptools'], check=True)
    return venv_path


def find_wheel(project_path: Path) -> Path:
    wheels = list(project_path.glob('dist/*.whl'))
    if len(wheels) != 1:
        raise Exception(f"Expected one wheel. Instead found: {wheels} in project {project_path.absolute()}")
    return wheels[0]


def install_wheel(venv_path: Path, wheel_path: Path, extras: Tuple[str, ...] = ()) -> None:
    if extras:
        extra_suffix = f"[{','.join(extras)}]"
    else:
        extra_suffix = ""
    subprocess.run([venv_path / 'bin' / 'pip', 'install', f"{wheel_path}{extra_suffix}"], check=True)


def test_install_local_wheel() -> None:
    with TemporaryDirectory() as tmpdir:
        venv_path = create_venv(Path(tmpdir))
        wheel_path = find_wheel(Path('.'))
        install_wheel(venv_path, wheel_path)
        print("Installed", wheel_path.absolute(), "to", venv_path)
        print(f"Activate with `source {venv_path}/bin/activate`")
        input("Press enter when the test has completed. The directory will be deleted.")


if __name__ == '__main__':
    test_install_local_wheel()
