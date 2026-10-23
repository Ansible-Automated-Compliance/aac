package cis_openshift_4

import rego.v1

test_openshift_compliant_configuration if {
    result := compliant with input as {
        "openshift": {
            "master_node": {
                "api_server": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "controller_manager": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "scheduler": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "etcd": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "cni": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "etcd_data": {
                    "permissions": 700,
                    "owner": "etcd",
                    "group": "etcd"
                },
                "admin_conf": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "scheduler_conf": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "controller_manager_conf": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "pki": {
                    "owner": "root",
                    "group": "root",
                    "cert_permissions": 644,
                    "key_permissions": 600
                }
            },
            "etcd": {
                "cert_file": "/etc/kubernetes/pki/etcd/server.crt",
                "key_file": "/etc/kubernetes/pki/etcd/server.key",
                "client_cert_auth": true,
                "auto_tls": false,
                "peer_cert_file": "/etc/kubernetes/pki/etcd/peer.crt",
                "peer_key_file": "/etc/kubernetes/pki/etcd/peer.key",
                "peer_client_cert_auth": true,
                "peer_auto_tls": false,
                "unique_ca": true
            },
            "control_plane": {
                "anonymous_auth": false,
                "basic_auth_file": "",
                "token_auth_file": "",
                "kubelet_https": true,
                "kubelet_client_certificate": "/etc/kubernetes/pki/apiserver-kubelet-client.crt",
                "kubelet_client_key": "/etc/kubernetes/pki/apiserver-kubelet-client.key",
                "kubelet_certificate_authority": "/etc/kubernetes/pki/ca.crt",
                "authorization_mode": ["Node", "RBAC"],
                "admission_plugins": ["EventRateLimit", "ServiceAccount", "NamespaceLifecycle", "PodSecurityPolicy", "NodeRestriction"],
                "insecure_bind_address": "",
                "insecure_port": 0,
                "secure_port": 6443,
                "profiling": false,
                "audit_log_path": "/var/log/audit.log",
                "audit_log_maxage": 30,
                "audit_log_maxbackup": 10,
                "audit_log_maxsize": 100,
                "request_timeout": 60,
                "service_account_lookup": true,
                "service_account_key_file": "/etc/kubernetes/pki/sa.key",
                "etcd_certfile": "/etc/kubernetes/pki/apiserver-etcd-client.crt",
                "etcd_keyfile": "/etc/kubernetes/pki/apiserver-etcd-client.key",
                "tls_cert_file": "/etc/kubernetes/pki/apiserver.crt",
                "tls_private_key_file": "/etc/kubernetes/pki/apiserver.key",
                "client_ca_file": "/etc/kubernetes/pki/ca.crt",
                "etcd_cafile": "/etc/kubernetes/pki/etcd/ca.crt",
                "encryption_provider_config": "/etc/kubernetes/encryption-config.yaml",
                "encryption_providers_secure": true,
                "strong_crypto_ciphers": true
            },
            "worker_node": {
                "kubelet_service": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "proxy_kubeconfig": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "kubelet_conf": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "ca": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "kubelet_config": {
                    "permissions": 644,
                    "owner": "root",
                    "group": "root"
                },
                "kubelet": {
                    "anonymous_auth": false,
                    "authorization_mode": "Webhook",
                    "client_ca_file": "/etc/kubernetes/pki/ca.crt",
                    "read_only_port": 0,
                    "streaming_connection_idle_timeout": 300,
                    "protect_kernel_defaults": true,
                    "make_iptables_util_chains": true,
                    "hostname_override": "",
                    "event_qps": 5,
                    "tls_cert_file": "/var/lib/kubelet/pki/kubelet.crt",
                    "tls_private_key_file": "/var/lib/kubelet/pki/kubelet.key",
                    "rotate_certificates": true,
                    "rotate_kubelet_server_certificate": true,
                    "strong_crypto_ciphers": true
                }
            },
            "kubernetes_policies": {
                "cluster_admin_restricted": true,
                "secrets_access_minimized": true,
                "wildcard_minimized": true,
                "pod_creation_minimized": true,
                "default_sa_restricted": true,
                "sa_tokens_restricted": true,
                "privileged_containers_minimized": true,
                "host_pid_minimized": true,
                "host_ipc_minimized": true,
                "host_network_minimized": true,
                "privilege_escalation_minimized": true,
                "root_containers_minimized": true,
                "net_raw_minimized": true,
                "added_capabilities_minimized": true,
                "capabilities_minimized": true,
                "cni_network_policies": true,
                "namespace_network_policies": true,
                "secrets_as_files": true,
                "external_secret_storage": true,
                "image_provenance": true,
                "admin_boundaries": true,
                "seccomp_profile": true,
                "security_context": true,
                "default_namespace_avoided": true
            },
            "network_policies": {
                "openshift_policies": true,
                "segmentation": true,
                "node_master_encryption": true,
                "pod_encryption": true,
                "ingress_controllers_secure": true,
                "routes_secure": true,
                "external_traffic_control": true,
                "service_mesh_secure": true,
                "sidecar_injection": true
            },
            "authentication": {
                "identity_providers": true,
                "ldap_secure": true,
                "oauth_secure": true,
                "service_account_auth": true,
                "mfa_enabled": true,
                "strong_passwords": true,
                "session_timeouts": true,
                "cert_based_auth": true,
                "cert_rotation": true
            },
            "authorization": {
                "rbac_configured": true,
                "role_bindings_reviewed": true,
                "cluster_role_bindings_minimized": true,
                "scc_configured": true,
                "custom_scc_secure": true,
                "privileged_scc_restricted": true,
                "admission_controllers": true,
                "custom_admission_secure": true
            },
            "logging": {
                "audit_enabled": true,
                "audit_retention": true,
                "audit_storage_secure": true,
                "application_logging": true,
                "log_aggregation": true,
                "sensitive_info_prevented": true,
                "log_monitoring": true,
                "security_events_monitored": true,
                "logs_backed_up": true,
                "log_integrity": true
            },
            "secrets_management": {
                "secrets_not_in_images": true,
                "encryption_at_rest": true,
                "encryption_in_transit": true,
                "rotation_configured": true,
                "access_monitored": true,
                "lifecycle_managed": true,
                "external_management": true,
                "secure_injection": true,
                "automated_cert_mgmt": true,
                "cert_expiration_monitoring": true
            }
        }
    }
    result == true
}

test_openshift_non_compliant_configuration if {
    result := compliant with input as {
        "openshift": {
            "master_node": {
                "api_server": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "controller_manager": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "scheduler": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "etcd": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "cni": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "etcd_data": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "admin_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "scheduler_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "controller_manager_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "pki": {
                    "owner": "nobody",
                    "group": "nobody",
                    "cert_permissions": 777,
                    "key_permissions": 777
                }
            },
            "etcd": {
                "cert_file": "",
                "key_file": "",
                "client_cert_auth": false,
                "auto_tls": true,
                "peer_cert_file": "",
                "peer_key_file": "",
                "peer_client_cert_auth": false,
                "peer_auto_tls": true,
                "unique_ca": false
            },
            "control_plane": {
                "anonymous_auth": true,
                "basic_auth_file": "/etc/kubernetes/basic_auth.csv",
                "token_auth_file": "/etc/kubernetes/known_tokens.csv",
                "kubelet_https": false,
                "kubelet_client_certificate": "",
                "kubelet_client_key": "",
                "kubelet_certificate_authority": "",
                "authorization_mode": ["AlwaysAllow"],
                "admission_plugins": ["AlwaysAdmit"],
                "insecure_bind_address": "0.0.0.0",
                "insecure_port": 8080,
                "secure_port": 0,
                "profiling": true,
                "audit_log_path": "",
                "audit_log_maxage": 0,
                "audit_log_maxbackup": 0,
                "audit_log_maxsize": 0,
                "request_timeout": 0,
                "service_account_lookup": false,
                "service_account_key_file": "",
                "etcd_certfile": "",
                "etcd_keyfile": "",
                "tls_cert_file": "",
                "tls_private_key_file": "",
                "client_ca_file": "",
                "etcd_cafile": "",
                "encryption_provider_config": "",
                "encryption_providers_secure": false,
                "strong_crypto_ciphers": false
            },
            "worker_node": {
                "kubelet_service": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "proxy_kubeconfig": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "kubelet_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "ca": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "kubelet_config": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "kubelet": {
                    "anonymous_auth": true,
                    "authorization_mode": "AlwaysAllow",
                    "client_ca_file": "",
                    "read_only_port": 10255,
                    "streaming_connection_idle_timeout": 0,
                    "protect_kernel_defaults": false,
                    "make_iptables_util_chains": false,
                    "hostname_override": "custom-hostname",
                    "event_qps": 0,
                    "tls_cert_file": "",
                    "tls_private_key_file": "",
                    "rotate_certificates": false,
                    "rotate_kubelet_server_certificate": false,
                    "strong_crypto_ciphers": false
                }
            },
            "kubernetes_policies": {
                "cluster_admin_restricted": false,
                "secrets_access_minimized": false,
                "wildcard_minimized": false,
                "pod_creation_minimized": false,
                "default_sa_restricted": false,
                "sa_tokens_restricted": false,
                "privileged_containers_minimized": false,
                "host_pid_minimized": false,
                "host_ipc_minimized": false,
                "host_network_minimized": false,
                "privilege_escalation_minimized": false,
                "root_containers_minimized": false,
                "net_raw_minimized": false,
                "added_capabilities_minimized": false,
                "capabilities_minimized": false,
                "cni_network_policies": false,
                "namespace_network_policies": false,
                "secrets_as_files": false,
                "external_secret_storage": false,
                "image_provenance": false,
                "admin_boundaries": false,
                "seccomp_profile": false,
                "security_context": false,
                "default_namespace_avoided": false
            },
            "network_policies": {
                "openshift_policies": false,
                "segmentation": false,
                "node_master_encryption": false,
                "pod_encryption": false,
                "ingress_controllers_secure": false,
                "routes_secure": false,
                "external_traffic_control": false,
                "service_mesh_secure": false,
                "sidecar_injection": false
            },
            "authentication": {
                "identity_providers": false,
                "ldap_secure": false,
                "oauth_secure": false,
                "service_account_auth": false,
                "mfa_enabled": false,
                "strong_passwords": false,
                "session_timeouts": false,
                "cert_based_auth": false,
                "cert_rotation": false
            },
            "authorization": {
                "rbac_configured": false,
                "role_bindings_reviewed": false,
                "cluster_role_bindings_minimized": false,
                "scc_configured": false,
                "custom_scc_secure": false,
                "privileged_scc_restricted": false,
                "admission_controllers": false,
                "custom_admission_secure": false
            },
            "logging": {
                "audit_enabled": false,
                "audit_retention": false,
                "audit_storage_secure": false,
                "application_logging": false,
                "log_aggregation": false,
                "sensitive_info_prevented": false,
                "log_monitoring": false,
                "security_events_monitored": false,
                "logs_backed_up": false,
                "log_integrity": false
            },
            "secrets_management": {
                "secrets_not_in_images": false,
                "encryption_at_rest": false,
                "encryption_in_transit": false,
                "rotation_configured": false,
                "access_monitored": false,
                "lifecycle_managed": false,
                "external_management": false,
                "secure_injection": false,
                "automated_cert_mgmt": false,
                "cert_expiration_monitoring": false
            }
        }
    }
    result == false
}

test_openshift_violations_count if {
    violations_result := violations with input as {
        "openshift": {
            "master_node": {
                "api_server": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "controller_manager": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "scheduler": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "etcd": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "cni": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "etcd_data": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "admin_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "scheduler_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "controller_manager_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "pki": {
                    "owner": "nobody",
                    "group": "nobody",
                    "cert_permissions": 777,
                    "key_permissions": 777
                }
            },
            "etcd": {
                "cert_file": "",
                "key_file": "",
                "client_cert_auth": false,
                "auto_tls": true,
                "peer_cert_file": "",
                "peer_key_file": "",
                "peer_client_cert_auth": false,
                "peer_auto_tls": true,
                "unique_ca": false
            },
            "control_plane": {
                "anonymous_auth": true,
                "basic_auth_file": "/etc/kubernetes/basic_auth.csv",
                "token_auth_file": "/etc/kubernetes/known_tokens.csv",
                "kubelet_https": false,
                "kubelet_client_certificate": "",
                "kubelet_client_key": "",
                "kubelet_certificate_authority": "",
                "authorization_mode": ["AlwaysAllow"],
                "admission_plugins": ["AlwaysAdmit"],
                "insecure_bind_address": "0.0.0.0",
                "insecure_port": 8080,
                "secure_port": 0,
                "profiling": true,
                "audit_log_path": "",
                "audit_log_maxage": 0,
                "audit_log_maxbackup": 0,
                "audit_log_maxsize": 0,
                "request_timeout": 0,
                "service_account_lookup": false,
                "service_account_key_file": "",
                "etcd_certfile": "",
                "etcd_keyfile": "",
                "tls_cert_file": "",
                "tls_private_key_file": "",
                "client_ca_file": "",
                "etcd_cafile": "",
                "encryption_provider_config": "",
                "encryption_providers_secure": false,
                "strong_crypto_ciphers": false
            },
            "worker_node": {
                "kubelet_service": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "proxy_kubeconfig": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "kubelet_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "ca": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "kubelet_config": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "kubelet": {
                    "anonymous_auth": true,
                    "authorization_mode": "AlwaysAllow",
                    "client_ca_file": "",
                    "read_only_port": 10255,
                    "streaming_connection_idle_timeout": 0,
                    "protect_kernel_defaults": false,
                    "make_iptables_util_chains": false,
                    "hostname_override": "custom-hostname",
                    "event_qps": 0,
                    "tls_cert_file": "",
                    "tls_private_key_file": "",
                    "rotate_certificates": false,
                    "rotate_kubelet_server_certificate": false,
                    "strong_crypto_ciphers": false
                }
            },
            "kubernetes_policies": {
                "cluster_admin_restricted": false,
                "secrets_access_minimized": false,
                "wildcard_minimized": false,
                "pod_creation_minimized": false,
                "default_sa_restricted": false,
                "sa_tokens_restricted": false,
                "privileged_containers_minimized": false,
                "host_pid_minimized": false,
                "host_ipc_minimized": false,
                "host_network_minimized": false,
                "privilege_escalation_minimized": false,
                "root_containers_minimized": false,
                "net_raw_minimized": false,
                "added_capabilities_minimized": false,
                "capabilities_minimized": false,
                "cni_network_policies": false,
                "namespace_network_policies": false,
                "secrets_as_files": false,
                "external_secret_storage": false,
                "image_provenance": false,
                "admin_boundaries": false,
                "seccomp_profile": false,
                "security_context": false,
                "default_namespace_avoided": false
            },
            "network_policies": {
                "openshift_policies": false,
                "segmentation": false,
                "node_master_encryption": false,
                "pod_encryption": false,
                "ingress_controllers_secure": false,
                "routes_secure": false,
                "external_traffic_control": false,
                "service_mesh_secure": false,
                "sidecar_injection": false
            },
            "authentication": {
                "identity_providers": false,
                "ldap_secure": false,
                "oauth_secure": false,
                "service_account_auth": false,
                "mfa_enabled": false,
                "strong_passwords": false,
                "session_timeouts": false,
                "cert_based_auth": false,
                "cert_rotation": false
            },
            "authorization": {
                "rbac_configured": false,
                "role_bindings_reviewed": false,
                "cluster_role_bindings_minimized": false,
                "scc_configured": false,
                "custom_scc_secure": false,
                "privileged_scc_restricted": false,
                "admission_controllers": false,
                "custom_admission_secure": false
            },
            "logging": {
                "audit_enabled": false,
                "audit_retention": false,
                "audit_storage_secure": false,
                "application_logging": false,
                "log_aggregation": false,
                "sensitive_info_prevented": false,
                "log_monitoring": false,
                "security_events_monitored": false,
                "logs_backed_up": false,
                "log_integrity": false
            },
            "secrets_management": {
                "secrets_not_in_images": false,
                "encryption_at_rest": false,
                "encryption_in_transit": false,
                "rotation_configured": false,
                "access_monitored": false,
                "lifecycle_managed": false,
                "external_management": false,
                "secure_injection": false,
                "automated_cert_mgmt": false,
                "cert_expiration_monitoring": false
            }
        }
    }
    count(violations_result) > 150
}

test_openshift_etcd_security if {
    etcd_cert_result := etcd_cert_key_configured with input as {
        "openshift": {
            "etcd": {
                "cert_file": "/etc/kubernetes/pki/etcd/server.crt",
                "key_file": "/etc/kubernetes/pki/etcd/server.key"
            }
        }
    }
    etcd_cert_result == true

    etcd_auth_result := etcd_client_cert_auth with input as {
        "openshift": {
            "etcd": {
                "client_cert_auth": true
            }
        }
    }
    etcd_auth_result == true

    etcd_auto_tls_result := etcd_auto_tls_disabled with input as {
        "openshift": {
            "etcd": {
                "auto_tls": true
            }
        }
    }
    etcd_auto_tls_result == false
}

test_openshift_control_plane_security if {
    anonymous_auth_result := anonymous_auth_disabled with input as {
        "openshift": {
            "control_plane": {
                "anonymous_auth": false
            }
        }
    }
    anonymous_auth_result == true

    authorization_mode_result := authorization_mode_includes_rbac with input as {
        "openshift": {
            "control_plane": {
                "authorization_mode": ["Node", "RBAC"]
            }
        }
    }
    authorization_mode_result == true

    insecure_port_result := insecure_port_disabled with input as {
        "openshift": {
            "control_plane": {
                "insecure_port": 0
            }
        }
    }
    insecure_port_result == true
}

test_openshift_worker_node_security if {
    kubelet_auth_result := kubelet_anonymous_auth_disabled with input as {
        "openshift": {
            "worker_node": {
                "kubelet": {
                    "anonymous_auth": false
                }
            }
        }
    }
    kubelet_auth_result == true

    readonly_port_result := kubelet_readonly_port_disabled with input as {
        "openshift": {
            "worker_node": {
                "kubelet": {
                    "read_only_port": 0
                }
            }
        }
    }
    readonly_port_result == true

    kernel_defaults_result := kubelet_protect_kernel_defaults with input as {
        "openshift": {
            "worker_node": {
                "kubelet": {
                    "protect_kernel_defaults": true
                }
            }
        }
    }
    kernel_defaults_result == true
}

test_openshift_kubernetes_policies if {
    cluster_admin_result := cluster_admin_role_restricted with input as {
        "openshift": {
            "kubernetes_policies": {
                "cluster_admin_restricted": true
            }
        }
    }
    cluster_admin_result == true

    privileged_containers_result := privileged_containers_minimized with input as {
        "openshift": {
            "kubernetes_policies": {
                "privileged_containers_minimized": true
            }
        }
    }
    privileged_containers_result == true

    default_namespace_result := default_namespace_avoided with input as {
        "openshift": {
            "kubernetes_policies": {
                "default_namespace_avoided": true
            }
        }
    }
    default_namespace_result == true
}

test_openshift_network_policies if {
    network_policies_result := openshift_network_policies_configured with input as {
        "openshift": {
            "network_policies": {
                "openshift_policies": true
            }
        }
    }
    network_policies_result == true

    encryption_result := node_master_traffic_encrypted with input as {
        "openshift": {
            "network_policies": {
                "node_master_encryption": true
            }
        }
    }
    encryption_result == true
}

test_openshift_authentication if {
    oauth_result := oauth_configuration_secure with input as {
        "openshift": {
            "authentication": {
                "oauth_secure": true
            }
        }
    }
    oauth_result == true

    mfa_result := mfa_enabled with input as {
        "openshift": {
            "authentication": {
                "mfa_enabled": true
            }
        }
    }
    mfa_result == true
}

test_openshift_authorization if {
    rbac_result := rbac_properly_configured with input as {
        "openshift": {
            "authorization": {
                "rbac_configured": true
            }
        }
    }
    rbac_result == true

    scc_result := scc_properly_configured with input as {
        "openshift": {
            "authorization": {
                "scc_configured": true
            }
        }
    }
    scc_result == true
}

test_openshift_logging if {
    audit_logging_result := audit_logging_enabled with input as {
        "openshift": {
            "logging": {
                "audit_enabled": true
            }
        }
    }
    audit_logging_result == true

    log_monitoring_result := log_monitoring_configured with input as {
        "openshift": {
            "logging": {
                "log_monitoring": true
            }
        }
    }
    log_monitoring_result == true
}

test_openshift_secrets_management if {
    secrets_encryption_result := secrets_encrypted_at_rest with input as {
        "openshift": {
            "secrets_management": {
                "encryption_at_rest": true
            }
        }
    }
    secrets_encryption_result == true

    cert_rotation_result := secret_rotation_configured with input as {
        "openshift": {
            "secrets_management": {
                "rotation_configured": true
            }
        }
    }
    cert_rotation_result == true
}

test_openshift_findings_structure if {
    findings_result := findings with input as {
        "openshift": {
            "master_node": {
                "api_server": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "controller_manager": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "scheduler": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "etcd": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "cni": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "etcd_data": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "admin_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "scheduler_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "controller_manager_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "pki": {
                    "owner": "nobody",
                    "group": "nobody",
                    "cert_permissions": 777,
                    "key_permissions": 777
                }
            },
            "etcd": {
                "cert_file": "",
                "key_file": "",
                "client_cert_auth": false,
                "auto_tls": true,
                "peer_cert_file": "",
                "peer_key_file": "",
                "peer_client_cert_auth": false,
                "peer_auto_tls": true,
                "unique_ca": false
            },
            "control_plane": {
                "anonymous_auth": true,
                "basic_auth_file": "/etc/kubernetes/basic_auth.csv",
                "token_auth_file": "/etc/kubernetes/known_tokens.csv",
                "kubelet_https": false,
                "kubelet_client_certificate": "",
                "kubelet_client_key": "",
                "kubelet_certificate_authority": "",
                "authorization_mode": ["AlwaysAllow"],
                "admission_plugins": ["AlwaysAdmit"],
                "insecure_bind_address": "0.0.0.0",
                "insecure_port": 8080,
                "secure_port": 0,
                "profiling": true,
                "audit_log_path": "",
                "audit_log_maxage": 0,
                "audit_log_maxbackup": 0,
                "audit_log_maxsize": 0,
                "request_timeout": 0,
                "service_account_lookup": false,
                "service_account_key_file": "",
                "etcd_certfile": "",
                "etcd_keyfile": "",
                "tls_cert_file": "",
                "tls_private_key_file": "",
                "client_ca_file": "",
                "etcd_cafile": "",
                "encryption_provider_config": "",
                "encryption_providers_secure": false,
                "strong_crypto_ciphers": false
            },
            "worker_node": {
                "kubelet_service": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "proxy_kubeconfig": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "kubelet_conf": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "ca": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "kubelet_config": {
                    "permissions": 777,
                    "owner": "nobody",
                    "group": "nobody"
                },
                "kubelet": {
                    "anonymous_auth": true,
                    "authorization_mode": "AlwaysAllow",
                    "client_ca_file": "",
                    "read_only_port": 10255,
                    "streaming_connection_idle_timeout": 0,
                    "protect_kernel_defaults": false,
                    "make_iptables_util_chains": false,
                    "hostname_override": "custom-hostname",
                    "event_qps": 0,
                    "tls_cert_file": "",
                    "tls_private_key_file": "",
                    "rotate_certificates": false,
                    "rotate_kubelet_server_certificate": false,
                    "strong_crypto_ciphers": false
                }
            },
            "kubernetes_policies": {
                "cluster_admin_restricted": false,
                "secrets_access_minimized": false,
                "wildcard_minimized": false,
                "pod_creation_minimized": false,
                "default_sa_restricted": false,
                "sa_tokens_restricted": false,
                "privileged_containers_minimized": false,
                "host_pid_minimized": false,
                "host_ipc_minimized": false,
                "host_network_minimized": false,
                "privilege_escalation_minimized": false,
                "root_containers_minimized": false,
                "net_raw_minimized": false,
                "added_capabilities_minimized": false,
                "capabilities_minimized": false,
                "cni_network_policies": false,
                "namespace_network_policies": false,
                "secrets_as_files": false,
                "external_secret_storage": false,
                "image_provenance": false,
                "admin_boundaries": false,
                "seccomp_profile": false,
                "security_context": false,
                "default_namespace_avoided": false
            },
            "network_policies": {
                "openshift_policies": false,
                "segmentation": false,
                "node_master_encryption": false,
                "pod_encryption": false,
                "ingress_controllers_secure": false,
                "routes_secure": false,
                "external_traffic_control": false,
                "service_mesh_secure": false,
                "sidecar_injection": false
            },
            "authentication": {
                "identity_providers": false,
                "ldap_secure": false,
                "oauth_secure": false,
                "service_account_auth": false,
                "mfa_enabled": false,
                "strong_passwords": false,
                "session_timeouts": false,
                "cert_based_auth": false,
                "cert_rotation": false
            },
            "authorization": {
                "rbac_configured": false,
                "role_bindings_reviewed": false,
                "cluster_role_bindings_minimized": false,
                "scc_configured": false,
                "custom_scc_secure": false,
                "privileged_scc_restricted": false,
                "admission_controllers": false,
                "custom_admission_secure": false
            },
            "logging": {
                "audit_enabled": false,
                "audit_retention": false,
                "audit_storage_secure": false,
                "application_logging": false,
                "log_aggregation": false,
                "sensitive_info_prevented": false,
                "log_monitoring": false,
                "security_events_monitored": false,
                "logs_backed_up": false,
                "log_integrity": false
            },
            "secrets_management": {
                "secrets_not_in_images": false,
                "encryption_at_rest": false,
                "encryption_in_transit": false,
                "rotation_configured": false,
                "access_monitored": false,
                "lifecycle_managed": false,
                "external_management": false,
                "secure_injection": false,
                "automated_cert_mgmt": false,
                "cert_expiration_monitoring": false
            }
        }
    }
    
    count(findings_result) == 1
    findings_result[0].title == "OpenShift 4.x Security Configuration Assessment"
    findings_result[0].severity == "HIGH"
    is_string(findings_result[0].description)
    is_string(findings_result[0].details)
    is_array(findings_result[0].violations)
    is_string(findings_result[0].remediation)
}