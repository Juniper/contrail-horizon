# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 NEC Corporation
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
import logging

from django.core.urlresolvers import reverse  # noqa
from django import template
from django.template import defaultfilters as filters
from django.utils.translation import ugettext_lazy as _  # noqa

from horizon import exceptions
from horizon import tables

from openstack_dashboard import api


LOG = logging.getLogger(__name__)

class NetFilterAction(tables.FilterAction):
    def filter(self, table, networks, filter_string):
        net = filter_string.lower()

        def comp(networks):
            if any([net in (networks.name or "").lower()]):
                return True
            return False

        return filter(comp, networks)


class CheckNetworkEditable(object):
    """Mixin class to determine the specified network is editable."""

    def allowed(self, request, datum=None):
        # Only administrator is allowed to create and manage shared networks.
        if datum and datum.shared:
            return False
        return True


class DeleteNetwork(CheckNetworkEditable, tables.DeleteAction):
    data_type_singular = _("Network")
    data_type_plural = _("Networks")

    def delete(self, request, network_id):
        try:
            # Retrieve existing subnets belonging to the network.
            subnets = api.neutron.subnet_list(request, network_id=network_id)
            LOG.debug('Network %s has subnets: %s' %
                      (network_id, [s.id for s in subnets]))
            for s in subnets:
                api.neutron.subnet_delete(request, s.id)
                LOG.debug('Deleted subnet %s' % s.id)

            api.neutron.network_delete(request, network_id)
            LOG.debug('Deleted network %s successfully' % network_id)
        except Exception:
            msg = _('Failed to delete network %s') % network_id
            LOG.info(msg)
            redirect = reverse("horizon:project:networking:index")
            exceptions.handle(request, msg, redirect=redirect)


class CreateNetwork(tables.LinkAction):
    name = "create"
    verbose_name = _("Create Network")
    url = "horizon:project:networking:create"
    classes = ("ajax-modal", "btn-create")


class EditNetwork(CheckNetworkEditable, tables.LinkAction):
    name = "update"
    verbose_name = _("Edit Network")
    url = "horizon:project:networking:update"
    classes = ("ajax-modal", "btn-edit")


class ModifyAttachedPolicies(CheckNetworkEditable, tables.LinkAction):
    name = "modify_attached_policies"
    verbose_name = _("Modify Associated Policies")
    url = "horizon:project:networking:modify_attached_policies"
    classes = ("ajax-modal", "btn-edit")

class CreateSubnet(CheckNetworkEditable, tables.LinkAction):
    name = "subnet"
    verbose_name = _("Add Subnet")
    url = "horizon:project:networking:addsubnet"
    classes = ("ajax-modal", "btn-create")


def get_subnets(network):
    template_name = 'project/networking/_network_ips.html'
    context = {"subnets": network.subnets}
    return template.loader.render_to_string(template_name, context)

def get_policies(network):
    if hasattr(network, 'policys'):
        template_name = 'project/networking/_network_policies.html'
        context = {"policies": network.policys}
        return template.loader.render_to_string(template_name, context)
    else:
        return '-'

class NetworksTable(tables.DataTable):
    name = tables.Column("name",
                         verbose_name=_("Name"),
                         link='horizon:project:networking:detail')
    subnets = tables.Column(get_subnets,
                            verbose_name=_("Subnets Associated"),)
    policies = tables.Column(get_policies,
                            verbose_name=_("Policies Associated"),)
    shared = tables.Column("shared", verbose_name=_("Shared"),
                           filters=(filters.yesno, filters.capfirst))
    #status = tables.Column("status", verbose_name=_("Status"))
    admin_state = tables.Column("admin_state",
                                verbose_name=_("Admin State"))

    class Meta:
        name = "networks"
        verbose_name = _("Networks")
        table_actions = (NetFilterAction, CreateNetwork, DeleteNetwork)
        row_actions = (EditNetwork, CreateSubnet, ModifyAttachedPolicies, DeleteNetwork)
