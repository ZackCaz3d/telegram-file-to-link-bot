# Copyright 2025 Aman
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

from fastapi import Request
from fastapi.responses import RedirectResponse

def admin_required(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse(
            url="/admin/login",
            status_code=303,
        )
