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
import netaddr

from django.core.urlresolvers import reverse  # noqa
from django.utils.translation import ugettext_lazy as _  # noqa

from horizon import exceptions
from horizon import forms
from horizon import messages
from horizon.forms import fields
from horizon import workflows

from openstack_dashboard import api

from contrail_openstack_dashboard.openstack_dashboard.api.contrail_quantum import *

LOG = logging.getLogger(__name__)

IPAM_CREATE_URL = "horizon:project:networking:ipam:create"

class CreateNetworkInfoAction(workflows.Action):
    net_name = forms.CharField(max_length=255,
                               label=_("Network Name"),
                               required=True)
    if api.neutron.is_port_profiles_supported():
        net_profile_id = forms.ChoiceField(label=_("Network Profile"))
    admin_state = forms.BooleanField(label=_("Admin State"),
                                     initial=True, required=False)
    if api.neutron.is_port_profiles_supported():
        def __init__(self, request, *args, **kwargs):
            super(CreateNetworkInfoAction, self).__init__(request,
                                                          *args, **kwargs)
            self.fields['net_profile_id'].choices = (
                self.get_network_profile_choices(request))

        def get_network_profile_choices(self, request):
            profile_choices = [('', _("Select a profile"))]
            for profile in self._get_profiles(request, 'network'):
                profile_choices.append((profile.id, profile.name))
            return profile_choices

        def _get_profiles(self, request, type_p):
            try:
                profiles = api.neutron.profile_list(request, type_p)
            except Exception:
                profiles = []
                msg = _('Network Profiles could not be retrieved.')
                exceptions.handle(request, msg)
            return profiles
    # TODO(absubram): Add ability to view network profile information
    # in the network detail if a profile is used.

    class Meta:
        name = _("Network")
        help_text = _("From here you can create a new network.\n"
                      "In addition a subnet associated with the network "
                      "can be created in the next panel and Policies can "
                      "be associated to this network")


class CreateNetworkInfo(workflows.Step):
    action_class = CreateNetworkInfoAction
    if api.neutron.is_port_profiles_supported():
        contributes = ("net_name", "admin_state", "net_profile_id")
    else:
        contributes = ("net_name", "admin_state")


class CreateSubnetInfoAction(workflows.Action):
    with_subnet = forms.BooleanField(label=_("Create Subnet"),
                                     initial=True, required=False)
    subnet_name = forms.CharField(max_length=255,
                                  label=_("Subnet Name"),
                                  required=False)
    ipam        = forms.DynamicTypedChoiceField(label=_("IPAM"),
                                 required=False,
                                 empty_value=None,
                                 add_item_link=IPAM_CREATE_URL,
                                 help_text=_("Choose IPAM that will be "
                                             "associated with the IP Block"))
    cidr = fields.IPField(label=_("Network Address"),
                          required=False,
                          initial="",
                          help_text=_("Network address in CIDR format "
                                      "(e.g. 192.168.0.0/24)"),
                          version=fields.IPv4 | fields.IPv6,
                          mask=True)
    ip_version = forms.ChoiceField(choices=[(4, 'IPv4'), (6, 'IPv6')],
                                   label=_("IP Version"))
    gateway_ip = fields.IPField(
        label=_("Gateway IP"),
        required=False,
        initial="",
        help_text=_("IP address of Gateway (e.g. 192.168.0.254) "
                    "The default value is the first IP of the "
                    "network address (e.g. 192.168.0.1 for "
                    "192.168.0.0/24). "
                    "If you use the default, leave blank. "
                    "If you want to use no gateway, "
                    "check 'Disable Gateway' below."),
        version=fields.IPv4,
        mask=False)
    no_gateway = forms.BooleanField(label=_("Disable Gateway"),
                                    initial=False, required=False)

    def __init__(self, request, *args, **kwargs):
        super(CreateSubnetInfoAction, self).__init__(request,
                                                      *args, **kwargs)
        tenant_id = self.request.user.tenant_id
        try:
            ipams = ipam_summary(self.request)
            if ipams:
                ipam_choices = [(ipam.id,
                                 "{0} ({1})".format(ipam.fq_name[2],
                                 ipam.fq_name[1]))
                                 for ipam in ipams]
                ipam_choices.append(('None', 'None'))
            else:
                ipam_choices = [('None', 'Create a new IPAM')]
        except:
            ipam_choices = [('None', 'None')]
            exceptions.handle(self.request, _('Unable to retrieve ipam list'))
        self.fields['ipam'].choices = ipam_choices

    class Meta:
        name = _("Subnet")
        help_text = _('You can create a subnet associated with the new '
                      'network, in which case "Network Address" must be '
                      'specified. If you wish to create a network WITHOUT a '
                      'subnet, uncheck the "Create Subnet" checkbox.')

    def _check_subnet_data(self, cleaned_data, is_create=True):
        cidr = cleaned_data.get('cidr')
        ipam = cleaned_data.get('ipam')
        ip_version = int(cleaned_data.get('ip_version'))
        gateway_ip = cleaned_data.get('gateway_ip')
        no_gateway = cleaned_data.get('no_gateway')
        if not cidr:
            msg = _('Specify "Network Address" or '
                    'clear "Create Subnet" checkbox.')
            raise forms.ValidationError(msg)
        if cidr:
            subnet = netaddr.IPNetwork(cidr)
            if subnet.version != ip_version:
                msg = _('Network Address and IP version are inconsistent.')
                raise forms.ValidationError(msg)
            if (ip_version == 4 and subnet.prefixlen == 32) or \
                    (ip_version == 6 and subnet.prefixlen == 128):
                msg = _("The subnet in the Network Address is too small (/%s)."
                        % subnet.prefixlen)
                raise forms.ValidationError(msg)
        if not no_gateway and gateway_ip:
            if netaddr.IPAddress(gateway_ip).version is not ip_version:
                msg = _('Gateway IP and IP version are inconsistent.')
                raise forms.ValidationError(msg)
        if not is_create and not no_gateway and not gateway_ip:
            msg = _('Specify IP address of gateway or '
                    'check "Disable Gateway".')
            raise forms.ValidationError(msg)

    def clean(self):
        cleaned_data = super(CreateSubnetInfoAction, self).clean()
        with_subnet = cleaned_data.get('with_subnet')
        if not with_subnet:
            return cleaned_data
        self._check_subnet_data(cleaned_data)
        return cleaned_data


class CreateSubnetInfo(workflows.Step):
    action_class = CreateSubnetInfoAction
    contributes = ("with_subnet", "subnet_name", "ipam", "cidr",
                   "ip_version", "gateway_ip", "no_gateway")


class CreateSubnetDetailAction(workflows.Action):
    enable_dhcp = forms.BooleanField(label=_("Enable DHCP"),
                                     initial=True, required=False)
    allocation_pools = forms.CharField(
        widget=forms.Textarea(),
        label=_("Allocation Pools"),
        help_text=_("IP address allocation pools. Each entry is "
                    "&lt;start_ip_address&gt;,&lt;end_ip_address&gt; "
                    "(e.g., 192.168.1.100,192.168.1.120) "
                    "and one entry per line."),
        required=False)
    dns_nameservers = forms.CharField(
        widget=forms.widgets.Textarea(),
        label=_("DNS Name Servers"),
        help_text=_("IP address list of DNS name servers for this subnet. "
                    "One entry per line."),
        required=False)
    host_routes = forms.CharField(
        widget=forms.widgets.Textarea(),
        label=_("Host Routes"),
        help_text=_("Additional routes announced to the hosts. "
                    "Each entry is &lt;destination_cidr&gt;,&lt;nexthop&gt; "
                    "(e.g., 192.168.200.0/24,10.56.1.254) "
                    "and one entry per line."),
        required=False)

    class Meta:
        name = _("Subnet Detail")
        help_text = _('You can specify additional attributes for the subnet.')

    def _convert_ip_address(self, ip, field_name):
        try:
            return netaddr.IPAddress(ip)
        except (netaddr.AddrFormatError, ValueError):
            msg = _('%(field_name)s: Invalid IP address '
                    '(value=%(ip)s)' % dict(
                        field_name=field_name, ip=ip))
            raise forms.ValidationError(msg)

    def _convert_ip_network(self, network, field_name):
        try:
            return netaddr.IPNetwork(network)
        except (netaddr.AddrFormatError, ValueError):
            msg = _('%(field_name)s: Invalid IP address '
                    '(value=%(network)s)' % dict(
                        field_name=field_name, network=network))
            raise forms.ValidationError(msg)

    def _check_allocation_pools(self, allocation_pools):
        for p in allocation_pools.split('\n'):
            p = p.strip()
            if not p:
                continue
            pool = p.split(',')
            if len(pool) != 2:
                msg = _('Start and end addresses must be specified '
                        '(value=%s)') % p
                raise forms.ValidationError(msg)
            start, end = [self._convert_ip_address(ip, "allocation_pools")
                          for ip in pool]
            if start > end:
                msg = _('Start address is larger than end address '
                        '(value=%s)') % p
                raise forms.ValidationError(msg)

    def _check_dns_nameservers(self, dns_nameservers):
        for ns in dns_nameservers.split('\n'):
            ns = ns.strip()
            if not ns:
                continue
            self._convert_ip_address(ns, "dns_nameservers")

    def _check_host_routes(self, host_routes):
        for r in host_routes.split('\n'):
            r = r.strip()
            if not r:
                continue
            route = r.split(',')
            if len(route) != 2:
                msg = _('Host Routes format error: '
                        'Destination CIDR and nexthop must be specified '
                        '(value=%s)') % r
                raise forms.ValidationError(msg)
            self._convert_ip_network(route[0], "host_routes")
            self._convert_ip_address(route[1], "host_routes")

    def clean(self):
        cleaned_data = super(CreateSubnetDetailAction, self).clean()
        self._check_allocation_pools(cleaned_data.get('allocation_pools'))
        self._check_host_routes(cleaned_data.get('host_routes'))
        self._check_dns_nameservers(cleaned_data.get('dns_nameservers'))
        return cleaned_data


class CreateSubnetDetail(workflows.Step):
    action_class = CreateSubnetDetailAction
    contributes = ("enable_dhcp", "allocation_pools",
                   "dns_nameservers", "host_routes")


class UpdateNetworkPolicyAction(workflows.MembershipAction):
    def __init__(self, request, *args, **kwargs):
        super(UpdateNetworkPolicyAction, self).__init__(request,
                                                       *args,
                                                       **kwargs)
        err_msg = _('Unable to retrieve Network Policy list. '
                    'Please try again later.')
        context = args[0]

        default_role_field_name = self.get_default_role_field_name()
        self.fields[default_role_field_name] = forms.CharField(required=False)
        self.fields[default_role_field_name].initial = 'member'

        field_name = self.get_member_field_name('member')
        self.fields[field_name] = forms.MultipleChoiceField(required=False)

        #Fetch the policy list and add to policy options
        all_policies = []
        try:
            all_policies = policy_summary(self.request)
        except Exception:
            exceptions.handle(request, err_msg)

        policy_list = [("{0}:{1}:{2}".format(
                                 policy.fq_name[0], policy.fq_name[1],
                                 policy.fq_name[2]),
                                 "{0} ({1})".format(
                                 policy.fq_name[2],
                                 policy.fq_name[1]))
                                 for policy in all_policies]

        self.fields[field_name].choices = policy_list

    class Meta:
        name = _("Associate Network Policies")
        slug = "update_network_policies"


class UpdateNetworkPolicy(workflows.UpdateMembersStep):
    action_class = UpdateNetworkPolicyAction
    help_text = _("You can associate Policies to this network by moving Policies "
                  "from the left column to the right column.")
    available_list_title = _("All Polices")
    members_list_title = _("Selected Policies")
    no_available_text = _("No Policies found.")
    no_members_text = _("No Policy selected.")
    show_roles = False
    #depends_on = ("network_id",)
    contributes = ("attached_policies",)

    def contribute(self, data, context):
        if data:
            member_field_name = self.get_member_field_name('member')
            context['attached_policies'] = data.get(member_field_name, [])
        return context

class CreateNetwork(workflows.Workflow):
    slug = "create_network"
    name = _("Create Network")
    finalize_button_name = _("Create")
    success_message = _('Created network "%s".')
    failure_message = _('Unable to create network "%s".')
    default_steps = (CreateNetworkInfo,
                     CreateSubnetInfo,
                     CreateSubnetDetail,
                     UpdateNetworkPolicy)

    def get_success_url(self):
        return reverse("horizon:project:networking:index")

    def get_failure_url(self):
        return reverse("horizon:project:networking:index")

    def format_status_message(self, message):
        name = self.context.get('net_name') or self.context.get('net_id', '')
        return message % name

    def _create_network(self, request, data):
        try:
            params = {'name': data['net_name'],
                      'admin_state_up': data['admin_state']}
            if api.neutron.is_port_profiles_supported():
                params['net_profile_id'] = data['net_profile_id']
            policy_list = []
            for pol in data['attached_policies']:
                policy_str  = pol.split(':')
                pol_fq_name = [policy_str[0],
                               policy_str[1],
                               policy_str[2]]
                policy_list.append(pol_fq_name)
            params['policys'] = policy_list
            network = api.neutron.network_create(request, **params)
            network.set_id_as_name_if_empty()
            self.context['net_id'] = network.id
            msg = _('Network "%s" was successfully created.') % network.name
            LOG.error(msg)
            return network
        except Exception as e:
            msg = (_('Failed to create network "%(network)s": %(reason)s') %
                   {"network": data['net_name'], "reason": e})
            LOG.info(msg)
            redirect = self.get_failure_url()
            exceptions.handle(request, msg, redirect=redirect)
            return False

    def _setup_subnet_parameters(self, params, data, is_create=True):
        """Setup subnet parameters

        This methods setups subnet parameters which are available
        in both create and update.
        """
        is_update = not is_create
        params['enable_dhcp'] = data['enable_dhcp']
        if is_create and data['allocation_pools']:
            pools = [dict(zip(['start', 'end'], pool.strip().split(',')))
                     for pool in data['allocation_pools'].split('\n')
                     if pool.strip()]
            params['allocation_pools'] = pools
        if data['host_routes'] or is_update:
            routes = [dict(zip(['destination', 'nexthop'],
                               route.strip().split(',')))
                      for route in data['host_routes'].split('\n')
                      if route.strip()]
            params['host_routes'] = routes
        if data['dns_nameservers'] or is_update:
            nameservers = [ns.strip()
                           for ns in data['dns_nameservers'].split('\n')
                           if ns.strip()]
            params['dns_nameservers'] = nameservers

    def _create_subnet(self, request, data, network=None, tenant_id=None,
                       no_redirect=False):
        if network:
            network_id = network.id
            network_name = network.name
        else:
            network_id = self.context.get('network_id')
            network_name = self.context.get('network_name')

        if data['ipam'] != 'None':
            try:
                ipam_obj = ipam_show(self.request, ipam_id=data['ipam'])
                params = {'network_id': network_id,
                          'name': data['subnet_name'],
                          'cidr': data['cidr'],
                          'ip_version': int(data['ip_version']),
                          'ipam_fq_name': ipam_obj.fq_name}
            except Exception as e:
                msg = _('Failed to read ipam "%(sub)s" for network "%(net)s": '
                        ' %(reason)s')
                if no_redirect:
                    redirect = None
                else:
                    redirect = self.get_failure_url()
                exceptions.handle(request,
                                  msg % {"sub": data['cidr'], "net": network_name,
                                         "reason": e},
                                  redirect=redirect)
        else:
            params = {'network_id': network_id,
                      'name': data['subnet_name'],
                      'cidr': data['cidr'],
                      'ip_version': int(data['ip_version'])}
        try:
            if tenant_id:
                params['tenant_id'] = tenant_id
            if data['no_gateway']:
                params['gateway_ip'] = None
            elif data['gateway_ip']:
                params['gateway_ip'] = data['gateway_ip']

            self._setup_subnet_parameters(params, data)

            subnet = api.neutron.subnet_create(request, **params)
            self.context['subnet_id'] = subnet.id
            msg = _('Subnet "%s" was successfully created.') % data['cidr']
            LOG.debug(msg)
            return subnet
        except Exception as e:
            msg = _('Failed to create subnet "%(sub)s" for network "%(net)s": '
                    ' %(reason)s')
            if no_redirect:
                redirect = None
            else:
                redirect = self.get_failure_url()
            exceptions.handle(request,
                              msg % {"sub": data['cidr'], "net": network_name,
                                     "reason": e},
                              redirect=redirect)
            return False

    def _delete_network(self, request, network):
        """Delete the created network when subnet creation failed"""
        try:
            api.neutron.network_delete(request, network.id)
            msg = _('Delete the created network "%s" '
                    'due to subnet creation failure.') % network.name
            LOG.debug(msg)
            redirect = self.get_failure_url()
            messages.info(request, msg)
            raise exceptions.Http302(redirect)
            #return exceptions.RecoverableError
        except Exception:
            msg = _('Failed to delete network "%s"') % network.name
            LOG.info(msg)
            redirect = self.get_failure_url()
            exceptions.handle(request, msg, redirect=redirect)

    def handle(self, request, data):
        network = self._create_network(request, data)
        if not network:
            return False
        # If we do not need to create a subnet, return here.
        if not data['with_subnet']:
            return True
        subnet = self._create_subnet(request, data, network, no_redirect=True)
        if subnet:
            return True
        else:
            self._delete_network(request, network)
            return False


class ModifyNetworkPolicyAction(workflows.MembershipAction):
    def __init__(self, request, *args, **kwargs):
        super(ModifyNetworkPolicyAction, self).__init__(request,
                                                       *args,
                                                       **kwargs)
        err_msg = _('Unable to retrieve Network Policy list. '
                    'Please try again later.')
        context = args[0]

        default_role_field_name = self.get_default_role_field_name()
        self.fields[default_role_field_name] = forms.CharField(required=False)
        self.fields[default_role_field_name].initial = 'member'

        field_name = self.get_member_field_name('member')
        self.fields[field_name] = forms.MultipleChoiceField(required=False)

        #Fetch the policy list and add to policy options
        all_policies = []
        try:
            all_policies = policy_summary(self.request)
        except Exception:
            exceptions.handle(request, err_msg)

        policy_list = [("{0}:{1}:{2}".format(
                                 policy.fq_name[0], policy.fq_name[1],
                                 policy.fq_name[2]),
                                 "{0} ({1})".format(
                                 policy.fq_name[2],
                                 policy.fq_name[1]))
                                 for policy in all_policies]

        self.fields[field_name].choices = policy_list

        network_id = context.get('network_id', '')
        attached_pols = []
        network_policys = []
        msg = _('Rahul Net od %s') % str(network_id)
        LOG.error(msg)
        if network_id:
            net_obj = network_get(request, network_id)
            try:
                network_policys = net_obj.policys
            except:
                pass
        if network_policys:
            attached_pols = ["{0}:{1}:{2}".format(
                                 policy[0], policy[1],
                                 policy[2])
                             for policy in network_policys]
        self.fields[field_name].initial = attached_pols
        msg = _('Rahul net policies %s') % str(network_policys)
        LOG.error(msg)
        msg = _('Rahul attached policies %s') % str(attached_pols)
        LOG.error(msg)

    def handle(self, request, data):
        attached_policies = data["attached_policies"]
        policy_list = []
        for pol in data['attached_policies']:
            policy_str  = pol.split(':')
            pol_fq_name = [policy_str[0],
                           policy_str[1],
                           policy_str[2]]
            policy_list.append(pol_fq_name)
        params = {'policys': policy_list}
        net_id = data['network_id']
        try:
            network_update(request,
                           network_id=net_id, **params)
        except Exception:
            exceptions.handle(request, _('Unable to modify Associated Policies.'))
            return False
        return True

    class Meta:
        name = _("Modify Network Policies")
        slug = "modify_network_policies"


class ModifyNetworkPolicy(workflows.UpdateMembersStep):
    action_class = ModifyNetworkPolicyAction
    help_text = _("You can associate Policies to this network by moving Policies "
                  "from the left column to the right column.")
    available_list_title = _("All Polices")
    members_list_title = _("Selected Policies")
    no_available_text = _("No Policies found.")
    no_members_text = _("No Policy selected.")
    show_roles = False
    depends_on = ("network_id",)
    contributes = ("attached_policies",)

    def contribute(self, data, context):
        if data:
            member_field_name = self.get_member_field_name('member')
            context['attached_policies'] = data.get(member_field_name, [])
        return context


class UpdateNetworkAttachedPolicies(workflows.Workflow):
    slug = "update_network_attached_policies"
    name = _("Modify Associated Policies")
    finalize_button_name = _("Save")
    success_message = _('Modified Associated Policies "%s".')
    failure_message = _('Unable to modify associated policies')
    success_url = "horizon:project:networking:index"
    default_steps = (ModifyNetworkPolicy,)
