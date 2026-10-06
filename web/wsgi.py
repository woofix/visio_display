# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from app import create_app

# Background tasks run in the dedicated scheduler service, never before fork.
app = create_app(start_scheduler=False)
