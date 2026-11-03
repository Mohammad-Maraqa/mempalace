"""Validation-only network guard; never part of the contribution branch."""

import ipaddress
import socket


def _loopback(host):
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _connect_guard(original):
    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not _loopback(address[0]):
            raise AssertionError("External connections are disabled for validation")
        return original(sock, address)

    return connect


socket.socket.connect = _connect_guard(socket.socket.connect)
socket.socket.connect_ex = _connect_guard(socket.socket.connect_ex)
_getaddrinfo = socket.getaddrinfo


def _local_addrinfo(host, *args, **kwargs):
    if not _loopback(host):
        raise socket.gaierror(socket.EAI_NONAME, "External DNS disabled for validation")
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _local_addrinfo
