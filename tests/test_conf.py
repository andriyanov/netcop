# pylint:disable=missing-module-docstring,missing-function-docstring,redefined-outer-name

import io
import sys
from pytest import fixture
from netcop import Conf

if sys.version_info >= (3, 3):
    from ipaddress import ip_address


@fixture
def conf():
    return Conf('''
snmp server 1
snmp server 2
stp mode mstp 1
interface IF1
    ip address 1.1.1.1
    ip address 2.2.2.2 secondary
    stp
        more stp
    !
    no ip redirects
!
interface IF2
    ip address 1.1.1.2
    no ip redirects
    ip unnumbered
    description hello world
    long-description "hello world" end
!
''')


@fixture
def jconf():
    return Conf('''
    forwarding-options {
        sampling { # Traffic is sampled and sent to a flow server.
            input {
                rate 1; # Samples 1 out of x packets (here, a rate of 1 sample per packet).
            }
        }
        family inet {
            output {
                flow-server 10.60.2.1 { # The IP address and port of the flow server.
                    port 2055;
                    version 5; # Records are sent to the flow server using version 5 format.
                }
                flow-inactive-timeout 15;
                flow-active-timeout 60;
                interface sp-2/0/0 { # Adding an interface here enables PIC-based sampling.
                    engine-id 5; # Engine statements are dynamic, but can be configured.
                    engine-type 55;
                    source-address 10.60.2.2; # You must configure this statement.
                }
                apply-groups [ one two three ]; # comment
            }
        }
    }
    ''')


def test1(conf):
    assert list(conf['snmp server']) == ['1', '2']

    assert conf['snmp server 1']
    assert 'snmp server 2' in conf

    assert not conf['snmp server 3']
    assert 'snmp server 3' not in conf

    assert 'stp mode mstp 1' in conf


def test2(conf):
    assert conf['interface if1 ip address 1.1.1.1']
    assert not conf['interface if1 ip address 1.1.1.2']
    assert not conf['interface if3 ip address']
    assert conf['stp mode mstp 1']


def test3(conf):
    assert conf['interface if1 no'].tail == 'ip redirects'


def test4(conf):
    assert len(conf['interface']) == 2
    assert list(conf['interface']) == ['IF1', 'IF2']


def test5(conf):
    expected = {
        'IF2': 'hello world'
    }
    actual = {}
    for ifname, iface in conf['interface'].items():
        if iface['description']:
            actual[ifname] = iface['description'].tail
    assert expected == actual

    assert conf['interface if2 long-description'].quoted == "hello world"


def test6(conf):
    assert conf['stp'].word == 'mode'
    assert conf['stp mode'].word == 'mstp'
    assert conf['stp mode mstp'].word == '1'


def test_repr(conf):
    assert repr(conf) == "Conf()['']"
    assert repr(conf['interface']) == "Conf()['interface']"
    assert repr(conf['interface if1 ip']) == "Conf()['interface IF1 ip']"
    assert repr(conf['interface IF3 ip']) == "Conf()"


def test_dump():
    conf = Conf("""
        snmp server 1
        stp mode mstp 1
        !
        interface IF1
            ip address 1.1.1.1
            ip address 2.2.2.2 secondary
        !
        interface IF2
            ip address 1.1.1.2
            no ip redirects
        !
    """)

    buff = io.StringIO()
    conf.dump(file=buff, indent="    ")
    assert buff.getvalue() == """
snmp server 1
stp mode mstp 1
!
interface IF1
    ip address 1.1.1.1
    ip address 2.2.2.2 secondary
!
interface IF2
    ip address 1.1.1.2
    no ip redirects
!
"""[1:]

    buff = io.StringIO()
    conf['interface if1 ip'].dump(file=buff, indent="    ")
    assert buff.getvalue() == """
[interface IF1 ip]
    address 1.1.1.1
    address 2.2.2.2 secondary
"""[1:]

    buff = io.StringIO()
    conf['stp'].dump(file=buff, indent="    ")
    assert buff.getvalue() == "[stp] mode mstp 1\n"

    jconf = Conf("""
        forwarding-options {
            sampling { # Traffic is sampled and sent to a flow server.
                input {
                    rate 1; # Samples 1 out of x packets (here, a rate of 1 sample per packet).
                }
            }
            family inet {
                output {
                    flow-server 10.60.2.1 { # The IP address and port of the flow server.
                        port 2055;
                        version 5; # Records are sent to the flow server using version 5 format.
                    }
                    flow-inactive-timeout 15;
                    flow-active-timeout 60;
                    interface sp-2/0/0 { # Adding an interface here enables PIC-based sampling.
                        engine-id 5; # Engine statements are dynamic, but can be configured.
                        engine-type 55;
                        source-address 10.60.2.2; # You must configure this statement.
                    }
                }
            }
        }
    """)

    buff = io.StringIO()
    jconf.dump(file=buff, indent="    ")
    assert buff.getvalue() == """
forwarding-options {
    sampling { # Traffic is sampled and sent to a flow server.
        input {
            rate 1; # Samples 1 out of x packets (here, a rate of 1 sample per packet).
        }
    }
    family inet {
        output {
            flow-server 10.60.2.1 { # The IP address and port of the flow server.
                port 2055;
                version 5; # Records are sent to the flow server using version 5 format.
            }
            flow-inactive-timeout 15;
            flow-active-timeout 60;
            interface sp-2/0/0 { # Adding an interface here enables PIC-based sampling.
                engine-id 5; # Engine statements are dynamic, but can be configured.
                engine-type 55;
                source-address 10.60.2.2; # You must configure this statement.
            }
        }
    }
}
"""[1:]

    buff = io.StringIO()
    key = 'forwarding-options family inet output flow-server'
    jconf[key].dump(file=buff, indent="    ")
    assert buff.getvalue() == """[%s] 10.60.2.1 { # The IP address and port of the flow server.
    port 2055;
    version 5; # Records are sent to the flow server using version 5 format.
""" % key


def test_junos(jconf):
    f_o = jconf['forwarding-options']
    assert f_o['sampling input rate'].int == 1
    assert f_o['family inet']
    if "ip_address" in globals():
        assert f_o['family inet output flow-server'].ips == [ip_address('10.60.2.1')]

    assert f_o['family inet output apply-groups'].junos_list == ['one', 'two', 'three']
    assert f_o['sampling input rate'].junos_list == ['1']


def test_expand(conf):
    assert list(conf.expand('interface * ip address *')) == [
        ('IF1', '1.1.1.1'),
        ('IF1', '2.2.2.2'),
        ('IF2', '1.1.1.2'),
    ]

    assert list(conf.expand('interface * ip blah *')) == []

    # assert list(conf.expand('interface')) == [(), ()]
