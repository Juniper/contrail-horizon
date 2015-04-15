# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 NTT MCL
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from django.conf.urls import patterns
from django.conf.urls import url

from contrail_openstack_dashboard.openstack_dashboard.dashboards.admin.l3routers.ports \
    import views

PORTS = r'^(?P<port_id>[^/]+)/%s$'

urlpatterns = patterns('horizon.dashboards.admin.networking.ports.views',
    url(PORTS % 'detail', views.DetailView.as_view(), name='detail'))
