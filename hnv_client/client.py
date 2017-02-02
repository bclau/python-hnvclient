# Copyright 2017 Cloudbase Solutions Srl
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

"""This module contains all the available HNV resources."""

import time
import uuid

from oslo_log import log as logging

from hnv_client.common import constant
from hnv_client.common import exception
from hnv_client.common import model
from hnv_client.common import utils
from hnv_client import config as hnv_config

LOG = logging.getLogger(__name__)
CONFIG = hnv_config.CONFIG


class _BaseHNVModel(model.Model):

    _endpoint = CONFIG.HNV.url

    resource_ref = model.Field(name="resource_ref", key="resourceRef",
                               is_property=False)
    """A relative URI to an associated resource."""

    resource_id = model.Field(name="resource_id", key="resourceId",
                              is_property=False,
                              default=lambda: str(uuid.uuid1()))
    """The resource ID for the resource. The value MUST be unique in
    the context of the resource if it is a top-level resource, or in the
    context of the direct parent resource if it is a child resource."""

    parent_id = model.Field(name="parent_id",
                            key="parentResourceID",
                            is_property=False, is_required=False,
                            is_read_only=True)
    """The parent resource ID field contains the resource ID that is
    associated with network objects that are ancestors of the necessary
    resource.
    """

    grandparent_id = model.Field(name="grandparent_id",
                                 key="grandParentResourceID",
                                 is_property=False, is_required=False,
                                 is_read_only=True)
    """The grand parent resource ID field contains the resource ID that
    is associated with network objects that are ancestors of the parent
    of the necessary resource."""

    operation_id = model.Field(name="operation_id", key="operation-id",
                               is_property=False, is_required=False,
                               is_read_only=True)
    """The value of the x-ms-request-id header returned by the resource
    provider."""

    instance_id = model.Field(name="instance_id", key="instanceId",
                              is_property=False)
    """The globally unique Id generated and used internally by the Network
    Controller. The mapping resource that enables the client to map between
    the instanceId and the resourceId."""

    resource_metadata = model.Field(name="resource_metadata",
                                    key="resourceMetadata",
                                    is_property=False, is_required=False)
    """Structured data that the client provides to the server. This is an
    optional element but it is suggested that all clients fill in the data
    that is applicable to them."""

    etag = model.Field(name="etag", key="etag", is_property=False)
    """An opaque string representing the state of the resource at the
    time the response was generated."""

    tags = model.Field(name="tags", key="tags", is_property=False,
                       is_required=False)

    provisioning_state = model.Field(name="provisioning_state",
                                     key="provisioningState",
                                     is_read_only=True, is_required=False)
    """Indicates the various states of the resource. Valid values are
    Deleting, Failed, Succeeded, and Updating."""

    @staticmethod
    def _get_client():
        """Create a new client for the HNV REST API."""
        return utils.get_client(url=CONFIG.HNV.url,
                                username=CONFIG.HNV.username,
                                password=CONFIG.HNV.password,
                                allow_insecure=CONFIG.HNV.https_allow_insecure,
                                ca_bundle=CONFIG.HNV.https_ca_bundle)

    @classmethod
    def get(cls, resource_id=None, parent_id=None):
        """Retrieves the required resources.

        :param resource_id:      The identifier for the specific resource
                                 within the resource type.
        :param parent_id:        The identifier for the specific ancestor
                                 resource within the resource type.
        """
        client = cls._get_client()
        endpoint = cls._endpoint.format(resource_id=resource_id or "",
                                        parent_id=parent_id or "")
        raw_data = client.get_resource(endpoint)
        if resource_id is None:
            return [cls.from_raw_data(item) for item in raw_data["value"]]
        else:
            return cls.from_raw_data(raw_data)

    @classmethod
    def remove(cls, resource_id, parent_id=None, wait=True, timeout=None):
        """Delete the required resource.

        :param resource_id:   The identifier for the specific resource
                              within the resource type.
        :param parent_id:     The identifier for the specific ancestor
                              resource within the resource type.
        :param wait:          Whether to wait until the operation is completed
        :param timeout:       The maximum amount of time required for this
                              operation to be completed.

        If optional :param wait: is True and timeout is None (the default),
        block if necessary until the resource is available. If timeout is a
        positive number, it blocks at most timeout seconds and raises the
        `TimeOut` exception if no item was available within that time.

        Otherwise (block is false), return a resource if one is immediately
        available, else raise the `NotFound` exception (timeout is ignored
        in that case).
        """
        client = cls._get_client()
        endpoint = cls._endpoint.format(resource_id=resource_id or "",
                                        parent_id=parent_id or "")
        client.remove_resource(endpoint)

        elapsed_time = 0
        while wait:
            try:
                client.get_resource(endpoint)
            except exception.NotFound:
                break

            elapsed_time += CONFIG.HNV.retry_interval
            if timeout and elapsed_time > timeout:
                raise exception.TimeOut("The request timed out.")
            time.sleep(CONFIG.HNV.retry_interval)

    def commit(self, wait=True, timeout=None):
        """Apply all the changes on the current model.

        :param wait:    Whether to wait until the operation is completed
        :param timeout: The maximum amount of time required for this
                        operation to be completed.

        If optional :param wait: is True and timeout is None (the default),
        block if necessary until the resource is available. If timeout is a
        positive number, it blocks at most timeout seconds and raises the
        `TimeOut` exception if no item was available within that time.

        Otherwise (block is false), return a resource if one is immediately
        available, else raise the `NotFound` exception (timeout is ignored
        in that case).
        """
        super(_BaseHNVModel, self).commit(wait=wait, timeout=timeout)
        client = self._get_client()
        endpoint = self._endpoint.format(resource_id=self.resource_id or "",
                                         parent_id=self.parent_id or "")
        request_body = self.dump(include_read_only=False)
        response = client.update_resource(endpoint, data=request_body)

        elapsed_time = 0
        while wait:
            response = client.get_resource(endpoint)
            properties = response.get("properties", {})
            provisioning_state = properties.get("provisioningState", None)
            if not provisioning_state:
                raise exception.ServiceException("The object doesn't contain "
                                                 "`provisioningState`.")
            if provisioning_state == constant.FAILED:
                raise exception.ServiceException(
                    "Failed to complete the required operation.")
            elif provisioning_state == constant.SUCCEEDED:
                break

            elapsed_time += CONFIG.HNV.retry_interval
            if timeout and elapsed_time > timeout:
                raise exception.TimeOut("The request timed out.")
            time.sleep(CONFIG.HNV.retry_interval)

        # Process the raw data from the update response
        fields = self.process_raw_data(response)
        # Set back the provision flag
        self._provision_done = False
        # Update the current model representation
        self._set_fields(fields)
        # Lock the current model
        self._provision_done = True

    @classmethod
    def from_raw_data(cls, raw_data):
        """Create a new model using raw API response."""
        raw_metadata = raw_data.get("resourceMetadata", None)
        if raw_metadata is not None:
            metadata = ResourceMetadata.from_raw_data(raw_metadata)
            raw_data["resourceMetadata"] = metadata

        return super(_BaseHNVModel, cls).from_raw_data(raw_data)


class Resource(model.Model):

    """Model for the resource references."""

    resource_ref = model.Field(name="resource_ref", key="resourceRef",
                               is_property=False, is_required=True)
    """A relative URI to an associated resource."""


class ResourceMetadata(model.Model):

    """Model for Resource Metadata.

    Structured data that the client provides to the server. This is an
    optional element but it is suggested that all clients fill in the
    data that is applicable to them.
    """

    client = model.Field(name="client", key="client",
                         is_property=False, is_required=False)
    """Indicates the client that creates or updates the resource.
    Although this element is optional, it is strongly recommended that it
    contain an appropriate value."""

    tenant_id = model.Field(name="tenant_id", key="tenantId",
                            is_property=False, is_required=False)
    """The identifier of the tenant in the client environment.
    Provides linkage between the resource in the Network Controller
    and the tenant in the client network."""

    group_id = model.Field(name="group_id", key="groupId",
                           is_property=False, is_required=False)
    """The identifier of the group that the tenant belongs to within
    the client environment. This is usually used in environments that
    contain multiple tenants that are aggregated into groups that the
    client manages. This provides linkage between the resource in the
    Network Controller and the group that the tenant belongs to in the
    client network."""

    resource_name = model.Field(name="resource_name", key="name",
                                is_property=False, is_required=False)
    """Indicates the globally unique name of the resource. If it
    is not assigned a value then it will be blank."""

    original_href = model.Field(name="original_href", key="originalHref",
                                is_property=False, is_required=False)
    """The original URI of the resource if the client uses a URI based
    system to organize resources."""


class IPPools(_BaseHNVModel):

    """Model for IP Pools.

    The ipPools resource represents the range of IP addresses from which IP
    addresses will be allocated for nodes within a subnet. The subnet is a
    logical or physical subnet inside a logical network.

    The ipPools for a virtual subnet are implicit. The start and end IP
    addresses of the pool of the virtual subnet is based on the IP prefix
    of the virtual subnet.
    """

    _endpoint = ("/networking/v1/logicalNetworks/{grandparent_id}"
                 "/logicalSubnets/{parent_id}/ipPools/{resource_id}")

    parent_id = model.Field(name="parent_id",
                            key="parentResourceID",
                            is_property=False, is_required=True,
                            is_read_only=True)
    """The parent resource ID field contains the resource ID that is
    associated with network objects that are ancestors of the necessary
    resource.
    """

    grandparent_id = model.Field(name="grandparent_id",
                                 key="grandParentResourceID",
                                 is_property=False, is_required=True,
                                 is_read_only=True)
    """The grand parent resource ID field contains the resource ID that
    is associated with network objects that are ancestors of the parent
    of the necessary resource."""

    start_ip_address = model.Field(name="start_ip_address",
                                   key="startIpAddress",
                                   is_required=True, is_read_only=False)
    """Start IP address of the pool.
    Note: This is an inclusive value so it is a valid IP address from
    this pool."""

    end_ip_address = model.Field(name="end_ip_address", key="endIpAddress",
                                 is_required=True, is_read_only=False)
    """End IP address of the pool.
    Note: This is an inclusive value so it is a valid IP address from
    this pool."""

    usage = model.Field(name="usage", key="usage",
                        is_required=False, is_read_only=True)
    """Statistics of the usage of the IP pool."""


class LogicalSubnetworks(_BaseHNVModel):

    """Logical subnetworks model.

    The logicalSubnets resource consists of a subnet/VLAN pair.
    The vlan resource is required; however it MAY contain a value of zero
    if the subnet is not associated with a vlan.
    """

    _endpoint = ("/networking/v1/logicalNetworks/{parent_id}"
                 "/logicalSubnets/{resource_id}")

    parent_id = model.Field(name="parent_id",
                            key="parentResourceID",
                            is_property=False, is_required=True,
                            is_read_only=True)
    """The parent resource ID field contains the resource ID that is
    associated with network objects that are ancestors of the necessary
    resource.
    """

    address_prefix = model.Field(name="address_prefix", key="addressPrefix")
    """Identifies the subnet id in form of ipAddresss/prefixlength."""

    vlan_id = model.Field(name="vlan_id", key="vlanID", is_required=True,
                          default=0)
    """Indicates the VLAN ID associated with the logical subnet."""

    routes = model.Field(name="routes", key="routes", is_required=False)
    """Indicates the routes that are contained in the logical subnet."""

    ip_pools = model.Field(name="ip_pools", key="ipPools",
                           is_required=False)
    """Indicates the IP Pools that are contained in the logical subnet."""

    dns_servers = model.Field(name="dns_servers", key="dnsServers",
                              is_required=False)
    """Indicates one or more DNS servers that are used for resolving DNS
    queries by devices or host connected to this logical subnet."""

    ip_configurations = model.Field(name="ip_configurations",
                                    key="ipConfigurations")
    """Indicates an array of IP configurations that are contained
    in the network interface."""

    network_interfaces = model.Field(name="network_interfaces",
                                     key="networkInterfaces",
                                     is_read_only=True)
    """Indicates an array of references to networkInterfaces resources
    that are attached to the logical subnet."""

    is_public = model.Field(name="is_public", key="isPublic")
    """Boolean flag specifying whether the logical subnet is a
    public subnet."""

    default_gateways = model.Field(name="default_gateways",
                                   key="defaultGateways")
    """A collection of one or more gateways for the subnet."""

    gateway_pools = model.Field(name="gateway_pools", key="gatewayPools",
                                is_required=False, is_read_only=True)
    """Indicates a collection of references to gatewayPools resources
    in which connections can be created. This information is populated
    at the time of subscription and can be changed only via the Service
    administrator portal."""

    @classmethod
    def from_raw_data(cls, raw_data):
        """Create a new model using raw API response."""
        ip_pools = []
        properties = raw_data["properties"]
        for raw_ip_pool in properties.get("ipPools", []):
            raw_ip_pool["parentResourceID"] = raw_data["resourceId"]
            raw_ip_pool["grandParentResourceID"] = raw_data["parentResourceID"]
            ip_pools.append(IPPools.from_raw_data(raw_ip_pool))
        properties["ipPools"] = ip_pools

        ip_configurations = []
        raw_settings = properties.get("ipConfigurations", [])
        for raw_configuration in raw_settings:
            ip_configuration = IPConfiguration.from_raw_data(raw_configuration)
            ip_configurations.append(ip_configuration)
        properties["ipConfigurations"] = ip_configurations

        return super(LogicalSubnetworks, cls).from_raw_data(raw_data)


class LogicalNetworks(_BaseHNVModel):

    """Logical networks model.

    The logicalNetworks resource represents a logical partition of physical
    network that is dedicated for a specific purpose.
    A logical network comprises of a collection of logical subnets.
    """

    _endpoint = "/networking/v1/logicalNetworks/{resource_id}"

    subnetworks = model.Field(name="subnetworks", key="subnets",
                              is_required=False, default=[])
    """Indicates the subnets that are contained in the logical network."""

    network_virtualization_enabled = model.Field(
        name="network_virtualization_enabled",
        key="networkVirtualizationEnabled", default=False, is_required=False)
    """Indicates if the network is enabled to be the Provider Address network
    for one or more virtual networks. Valid values are `True` or `False`.
    The default is `False`."""

    virtual_networks = model.Field(name="virtual_networks",
                                   key="virtualNetworks",
                                   is_read_only=True)
    """Indicates an array of virtualNetwork resources that are using
    the network."""

    @classmethod
    def from_raw_data(cls, raw_data):
        """Create a new model using raw API response."""
        properties = raw_data["properties"]

        subnetworks = []
        for raw_subnet in properties.get("subnets", []):
            raw_subnet["parentResourceID"] = raw_data["resourceId"]
            subnetworks.append(LogicalSubnetworks.from_raw_data(raw_subnet))
        properties["subnets"] = subnetworks

        virtual_networks = []
        for raw_network in properties.get("virtualNetworks", []):
            virtual_networks.append(Resource.from_raw_data(raw_network))
        properties["virtualNetworks"] = virtual_networks

        return super(LogicalNetworks, cls).from_raw_data(raw_data)


class IPConfiguration(_BaseHNVModel):

    """IP Configuration Model.

    This resource represents configuration information for IP addresses:
    allocation method, actual IP address, membership of a logical or virtual
    subnet, load balancing and access control information.
    """

    _endpoint = ("/networking/v1/networkInterfaces/{parent_id}"
                 "/ipConfigurations/{resource_id}")

    parent_id = model.Field(name="parent_id",
                            key="parentResourceID",
                            is_property=False, is_required=True,
                            is_read_only=True)
    """The parent resource ID field contains the resource ID that is
    associated with network objects that are ancestors of the necessary
    resource.
    """

    access_controll_list = model.Field(name="access_controll_list",
                                       key="accessControlList",
                                       is_required=False)
    """Indicates a reference to an accessControlList resource that defines
    the ACLs in and out of the IP Configuration."""

    backend_address_pools = model.Field(
        name="backend_address_pools", key="loadBalancerBackendAddressPools",
        is_required=False, is_read_only=True)
    """Reference to backendAddressPools child resource of loadBalancers
    resource."""

    inbound_nat_rules = model.Field(
        name="loadBalancerInboundNatRules", key="loadBalancerInboundNatRules",
        is_required=False)
    """Reference to inboundNatRules child resource of loadBalancers
    resource."""

    private_ip_address = model.Field(
        name="private_ip_address", key="privateIPAddress",
        is_required=False)
    """Indicates the private IP address of the IP Configuration."""

    private_ip_allocation_method = model.Field(
        name="private_ip_allocation_method", key="privateIPAllocationMethod",
        is_required=False)
    """Indicates the allocation method (Static or Dynamic)."""

    public_ip_address = model.Field(
        name="public_ip_address", key="privateIpAddress",
        is_required=False)
    """Indicates the public IP address of the IP Configuration."""

    service_insertion = model.Field(
        name="service_insertion", key="serviceInsertion",
        is_required=False)
    """Indicates a reference to a serviceInsertion resource that defines
    the service insertion in and out of the IP Configuration."""

    subnet = model.Field(name="subnet", key="subnet", is_read_only=True)
    """Indicates a reference to the subnet resource that the IP Configuration
    is connected to."""


class DNSSettings(model.Model):

    """Model for DNS Setting for Network Interfaces."""

    dns_servers = model.Field(name="dns_servers", key="dnsServers",
                              is_property=False, is_required=False)
    """Indicates an array of IP Addresses that the network interface
    resource will use for the DNS servers."""


class QosSettings(model.Model):

    """Qos Settings Model."""

    outbound_reserved_value = model.Field(name="outbound_reserved_value",
                                          key="outboundReservedValue",
                                          is_required=False,
                                          is_property=False)
    """If outboundReservedMode is "absolute" then the value indicates the
    bandwidth, in Mbps, guaranteed to the virtual port for transmission
    (egress)."""

    outbound_maximum_mbps = model.Field(name="outbound_maximum_mbps",
                                        key="outboundMaximumMbps",
                                        is_required=False,
                                        is_property=False)
    """Indicates the maximum permitted send-side bandwidth, in Mbps,
    for the virtual port (egress)."""

    inbound_maximum_mbps = model.Field(name="inbound_maximum_mbps",
                                       key="inboundMaximumMbps",
                                       is_required=False,
                                       is_property=False)
    """Indicates the maximum permitted receive-side bandwidth for the
    virtual port (ingress) in Mbps."""


class PortSettings(model.Model):

    """Port Settings Model."""

    mac_spoofing = model.Field(name="mac_spoofing", key="macSpoofingEnabled",
                               is_required=False, is_property=False)
    """Specifies whether virtual machines can change the source MAC
    address in outgoing packets to one not assigned to them."""

    arp_guard = model.Field(name="arp_guard", key="arpGuardEnabled",
                            is_required=False, is_property=False)
    """Specifies whether ARP guard is enabled or not. ARP guard
    will allow only addresses specified in ArpFilter to pass through
    the port."""

    dhcp_guard = model.Field(name="dhcp_guard", key="dhcpGuardEnabled",
                             is_required=False, is_property=False)
    """Specifies the number of broadcast, multicast, and unknown
    unicast packets per second a virtual machine is allowed to
    send through the specified virtual network adapter."""

    storm_limit = model.Field(name="storm_limit", key="stormLimit",
                              is_required=False, is_property=False)
    """Specifies the number of broadcast, multicast, and unknown
    unicast packets per second a virtual machine is allowed to
    send through the specified virtual network adapter."""

    port_flow_limit = model.Field(name="port_flow_limit",
                                  key="portFlowLimit",
                                  is_required=False, is_property=False)
    """Specifies the maximum number of flows that can be executed
    for the port."""

    vmq_weight = model.Field(name="vmq_weight", key="vmqWeight",
                             is_required=False, is_property=False)
    """Specifies whether virtual machine queue (VMQ) is to be
    enabled on the virtual network adapter."""

    iov_weight = model.Field(name="iov_weight", key="iovWeight",
                             is_required=False, is_property=False)
    """Specifies whether single-root I/O virtualization (SR-IOV) is to
    be enabled on this virtual network adapter."""

    iov_interrupt_moderation = model.Field(name="iov_interrupt_moderation",
                                           key="iovInterruptModeration",
                                           is_required=False,
                                           is_property=False)
    """Specifies the interrupt moderation value for a single-root I/O
    virtualization (SR-IOV) virtual function assigned to a virtual
    network adapter."""

    iov_queue_pairs = model.Field(name="iov_queue_pairs",
                                  key="iovQueuePairsRequested",
                                  is_required=False, is_property=False)
    """Specifies the number of hardware queue pairs to be allocated
    to an SR-IOV virtual function."""

    qos_settings = model.Field(name="qos_settings", key="qosSettings",
                               is_required=False, is_property=False)

    @classmethod
    def from_raw_data(cls, raw_data):
        """Create a new model using raw API response."""
        raw_settings = raw_data.get("qosSettings", {})
        qos_settings = QosSettings.from_raw_data(raw_settings)
        raw_data["qosSettings"] = qos_settings
        return super(PortSettings, cls).from_raw_data(raw_data)


class ConfigurationState(model.Model):

    """Model for configuration state."""

    uuid = model.Field(name="uuid", key="id",
                       is_property=False, is_required=False)
    status = model.Field(name="status", key="status",
                         is_property=False, is_required=False)
    last_update = model.Field(name="last_update", key="lastUpdatedTime",
                              is_property=False, is_required=False)
    detailed_info = model.Field(name="detailed_info", key="detailedInfo",
                                is_property=False, is_required=False)
    interface_errors = model.Field(name="interface_errors",
                                   key="virtualNetworkInterfaceErrors",
                                   is_property=False, is_required=False)
    host_errors = model.Field(name="host_erros", key="hostErrors",
                              is_property=False, is_required=False)


class NetworkInterfaces(_BaseHNVModel):

    """Network Interface Model.

    The networkInterfaces resource specifies the configuration of either
    a host virtual interface (host vNIC) or a virtual server NIC (VMNIC).
    """

    _endpoint = "/networking/v1/networkInterfaces/{resource_id}"

    configuration_state = model.Field(name="configuration_state",
                                      key="configurationState",
                                      is_read_only=True, is_required=False)

    dns_settings = model.Field(name="dns_settings", key="dnsSettings",
                               is_read_only=False)
    """Indicates the DNS settings of this network interface."""

    ip_configurations = model.Field(name="ip_configurations",
                                    key="ipConfigurations")
    """Indicates an array of IP configurations that are contained
    in the network interface."""

    is_host = model.Field(name="is_host",
                          key="isHostVirtualNetworkInterface")
    """True if this is a host virtual interface (host vNIC)
    False if this is a virtual server NIC (VMNIC)."""

    is_primary = model.Field(name="is_primary", key="isPrimary",
                             default=True, is_static=True)
    """`True` if this is the primary interface and the default
    value if the property is not set or `False` if this is a
    secondary interface."""

    is_multitenant_stack = model.Field(name="is_multitenant_stack",
                                       key="isMultitenantStack",
                                       default=False)
    """`True` if allows the NIC to be part of multiple virtual networks
    or `False` if the opposite."""

    internal_dns_name = model.Field(name="internal_dns_name",
                                    key="internalDnsNameLabel")
    """Determines the name that will be registered in iDNS
    when the iDnsServer resource is configured."""

    server = model.Field(name="server", key="server",
                         is_read_only=True)
    """Indicates a reference to the servers resource for the
    machine that is currently hosting the virtual machine to
    which this network interface belongs."""

    port_settings = model.Field(name="port_settings", key="portSettings")
    """A PortSettings object."""

    mac_address = model.Field(name="mac_address", key="privateMacAddress")
    """Indicates the private MAC address of this network interface."""

    mac_allocation_method = model.Field(name="mac_allocation_method",
                                        key="privateMacAllocationMethod")
    """Indicates the allocation scheme of the MAC for this
    network interface."""

    service_insertion_elements = model.Field(
        name="service_insertion_elements", key="serviceInsertionElements",
        is_read_only=True)
    """Indicates an array of serviceInsertions resources that
    this networkInterfaces resource is part of."""

    @classmethod
    def from_raw_data(cls, raw_data):
        """Create a new model using raw API response."""
        properties = raw_data["properties"]

        ip_configurations = []
        raw_settings = properties.get("ipConfigurations", [])
        for raw_configuration in raw_settings:
            ip_configuration = IPConfiguration.from_raw_data(raw_configuration)
            ip_configurations.append(ip_configuration)
        properties["ipConfigurations"] = ip_configurations

        raw_settings = properties.get("dnsSettings", {})
        dns_settings = DNSSettings.from_raw_data(raw_settings)
        properties["dnsSettings"] = dns_settings

        raw_settings = properties.get("portSettings", {})
        port_settings = PortSettings.from_raw_data(raw_settings)
        properties["portSettings"] = port_settings

        raw_state = properties.get("configurationState", {})
        configuration = ConfigurationState.from_raw_data(raw_state)
        properties["configurationState"] = configuration

        return super(NetworkInterfaces, cls).from_raw_data(raw_data)


class SubNetworks(_BaseHNVModel):

    """SubNetwork Model.

    The subnets resource is used to create Virtual Subnets (VSIDs) under
    a tenant's virtual network (RDID). The user can specify the addressPrefix
    to use for the subnets, the accessControl Lists to protect the subnets,
    the routeTable to be applied to the subnet, and optionally the service
    insertion to use within the subnet.
    """

    _endpoint = ("/networking/v1/virtualNetworks/{parent_id}"
                 "/subnets/{resource_id}")

    parent_id = model.Field(name="parent_id",
                            key="parentResourceID",
                            is_property=False, is_required=True,
                            is_read_only=True)
    """The parent resource ID field contains the resource ID that is
    associated with network objects that are ancestors of the necessary
    resource.
    """

    address_prefix = model.Field(name="address_prefix", key="addressPrefix",
                                 is_required=True)
    """Indicates the address prefix that defines the subnet. The value is
    in the format of 0.0.0.0/0. This value must not overlap with other
    subnets in the virtual network and must fall in the addressPrefix defined
    in the virtual network."""

    access_controll_list = model.Field(name="access_controll_list",
                                       key="accessControlList",
                                       is_required=False)
    """Indicates a reference to an accessControlLists resource that defines
    the ACLs in and out of the subnet."""

    service_insertion = model.Field(name="service_insertion",
                                    key="serviceInsertion",
                                    is_required=False)
    """Indicates a reference to a serviceInsertions resource that defines the
    service insertion to be applied to the subnet."""

    route_table = model.Field(name="route_table", key="routeTable",
                              is_required=False)
    """Indicates a reference to a routeTable resource that defines the tenant
    routes to be applied to the subnet."""

    ip_configuration = model.Field(name="ip_configuration",
                                   key="ipConfigurations",
                                   is_read_only=False)
    """Indicates an array of references of networkInterfaces resources that
    are connected to the subnet."""

    @classmethod
    def from_raw_data(cls, raw_data):
        """Create a new model using raw API response."""
        properties = raw_data["properties"]

        ip_configurations = []
        for raw_config in properties.get("ipConfigurations", []):
            ip_configurations.append(IPConfiguration.from_raw_data(raw_config))
        properties["ipConfigurations"] = ip_configurations

        acl = properties.get("accessControlList")
        if acl:
            properties["accessControlList"] = Resource.from_raw_data(acl)

        return super(SubNetworks, cls).from_raw_data(raw_data)


class VirtualNetworks(_BaseHNVModel):

    """Virtual Network Model.

    This resource is used to create a virtual network using HNV for tenant
    overlays. The default encapsulation for virtualNetworks is Virtual
    Extensible LAN but this can be changed by updating the virtual
    NetworkManager resource. Similarly, the HNV Distributed Router is enabled
    by default but this can be overridden using the virtualNetworkManager
    resource.
    """

    _endpoint = "/networking/v1/virtualNetworks/{resource_id}"

    configuration_state = model.Field(name="configuration_state",
                                      key="configurationState",
                                      is_read_only=True)
    """Indicates the last known running state of this resource."""

    address_space = model.Field(name="address_space",
                                key="addressSpace",
                                is_required=True)
    """Indicates the address space of the virtual network."""

    dhcp_options = model.Field(name="dhcp_options", key="dhcpOptions",
                               is_required=False)
    """Indicates the DHCP options used by servers in the virtual
    network."""

    subnetworks = model.Field(name="subnetworks", key="subnets",
                              is_required=False)
    """Indicates the subnets that are on the virtual network."""

    logical_network = model.Field(name="logical_network",
                                  key="logicalNetwork",
                                  is_required=True)
    """Indicates a reference to the networks resource that is the
    underlay network which the virtual network runs on."""

    @classmethod
    def from_raw_data(cls, raw_data):
        """Create a new model using raw API response."""
        properties = raw_data["properties"]

        subnetworks = []
        for raw_subnet in properties.get("subnets", []):
            raw_subnet["parentResourceID"] = raw_data["resourceId"]
            subnetworks.append(SubNetworks.from_raw_data(raw_subnet))
        properties["subnets"] = subnetworks

        raw_network = properties.get("logicalNetwork")
        if raw_network:
            properties["logicalNetwork"] = Resource.from_raw_data(raw_network)

        raw_config = properties.get("configurationState")
        if raw_config:
            config = ConfigurationState.from_raw_data(raw_config)
            properties["configurationState"] = config

        return super(VirtualNetworks, cls).from_raw_data(raw_data)