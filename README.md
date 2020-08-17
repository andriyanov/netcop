# Netcop — NETwork COnfig Parser

This Python library helps navigating and querying textual (CLI-style) configs of network devices. It may be useful for solving such problems like:
- listing a device interfaces
- extracting IP address or VLAN configurations of a network interface
- checking if a particular option is properly set in all the relevant blocks

It does not support modifying and comparing of configs, as the [CiscoConfigParse][1] does, but provides a nice and simple query API.

## Installation
Netcop works with both Python 2.7 and Python 3.

To install it as a package, use this command:

    python -m pip install https://github.com/andriyanov/netcop/archive/master.tar.gz


## Vendor compatibility
Netcop works by parsing hierarchical text configs that use newline-separated statements, whitespace indentation of blocks and keywords prefixes as a config path. Thus, it is not limited to a particular vendor's syntax.

In particular, these types of configs are supported by Netcop:
- Cisco IOS, NX-OS, IOS-XR
- Huawei VRP
- Juniper JunOS
- Quagga / FRR

There should be many more of them, I have not checked others yet.

However, Netcop does not have any idea of the config semantics — it can't guess the type of data relying by a given config path whether it is a list, an int, a string or an IP address. It's always a user who knows the semantics and treats a given path to be of a particular type.


## Usage guide

Let's say we have this simple config to parse:
```python
c = netcop.Conf('''
interface Port-channel1
    no ip address
!
interface Port-channel2
    ip address 10.0.0.2 255.255.0.0
    ip address 10.1.0.2 255.255.0.0 secondary
!
interface Loopback0
  ip address 1.1.1.1 255.255.255.255
!
''')
```

Below are some examples of processing this config.

### Indexing
The result of parsing looks very much like a Python `dict` and Netcop tries hard to keep its API similar to what you can expect from a dict.

The key operation you can do with a `Conf` object is to get a sub-object by a string key with the `[]` operator.

Then we just use any of the following expressions to get a part (slice) of the config as another `Conf` object that has the same API for subsequent queries:
- `c['interface']`
- `c['interface Port-channel1']`
- `c['interface Port-channel2 ip address']`


To illustrate the way a config tree is organized, let's take a look at these three queries that return the same result:
- `c['interface Port-channel2 ip address']`
- `c['interface']['Port-channel2 ip']['address']`
- `c['interface']['Port-channel2']['ip address']`

Unlike the dict's `[]`, this operator never causes the `KeyError` exception, it returns an empty `Conf` object instead.

### Iterating

To obtain a sequence of interface names, you just need to use `.keys()` method:

```python
[i for i in c['interface'].keys()]
```
Output:

    ['Port-channel1', 'Port-channel2', 'Loopback0']

Just as it is with a dict, you can get the same result by iterating over an object:
```python
[i for i in c['interface']]
```

Likewise, to get IP addresses assigned to all the interfaces, use this snippet:
```python
for ifname in c['interface']:
    for ip in c['interface'][ifname]['ip address']:
        print(ifname, ip)
```
Output:

    Port-channel2 10.0.0.2
    Port-channel2 10.1.0.2
    Loopback0 1.1.1.1

Just as it is with a `dict`, you can use `.items()` to avoid redundant key lookups (resulting output is the same):
```python
for ifname, iface_c in c['interface'].items():
    for ip in iface_c['ip address']:
        print(ifname, ip)
```

### Checking
In a bool context a `Conf` object returns if it's empty, or in other words, if a specified config path exists.
```python
# __bool__ operator works:
bool(c) == True
bool(c['interface Loopback0']) == True
bool(c['interface Blah']) == False
bool(c['interface Port-channel1 no ip address']) == True
bool(c['interface Port-channel2 no ip address']) == False

# same for __contains__ operator:
('interface Loopback0' in c) == True
('interface Blah' in c) == False
('interface Port-channel1 no ip address' in c) == True
('interface Port-channel2 no ip address' in c) == False
```

### Getting values
So far, we have seen how to iterate over multiple values by a given path. What if we're sure that there is only one value for a path? Then you can use any of the scalar properties of a `Conf` object:
- `.word` - a single string keyword
- `.int` - an integer value
- `.ip`, `.cidr` (*since Python 3.3*) - a `IPAddress` or `IPNetwork` object from the `ipaddress` standard library
- `.tail` - all the tailing keywords as a string

You should note that in contrast to indexing and iterating operations that can never fail, the scalar getters can raise `KeyError` or `TypeError` if there are no values for a given path, or if there are multiple ones.

Here is an example:

```python
c['interface Loopback0 ip address'].word == '1.1.1.1'
c['interface Loopback0 ip address'].ip == IPv4Address('1.1.1.1')
c['interface Loopback0 ip address'].tail == '1.1.1.1 255.55.255.255'
c['interface Port-channel2 ip address'].ip  # KeyError raised
```

There are also list properties `.ints`, `.ips` and `.cidrs`, which are just type-converting iterators and shorthands for expressions like `[int(x) for x in c]`.

### Wildcard indexing
Netcop does not use regular expressions to make index lookups, it requires exact keywords in the config path. However, there are cases when it is useful to specify a config path with a pattern:
```python
for ifname, ip in c.expand('interface po* ip address *'):
    print(ifname, ip)
```
Resulting output:

    Port-channel2 10.0.0.2
    Port-channel2 10.1.0.2

The `.expand()` method iterates over all possible paths in a config by a given selector with wildcards using glob syntax. It returns tuples with the length equal to the number of wildcard placeholders in a given key.


[1]: https://github.com/mpenning/ciscoconfparse
