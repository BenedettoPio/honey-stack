#!/bin/bash
# Plugin DevStack di Honey-Stack.
# Si attiva in local.conf con:
#   enable_plugin honey-stack https://github.com/BenedettoPio/honey-stack main

# ==================================================================
# FASE "stack install" (./stack.sh): installazione del pacchetto
# ==================================================================

# Installa il pacchetto nel venv di DevStack (modalita' sviluppo)
function install_honeystack {
    setup_develop $HONEYSTACK_DIR
}

# ==================================================================
# FASE "stack post-config" (./stack.sh): configurazione di Keystone,
# account, file di configurazione e pannelli di Horizon
# ==================================================================

# Keystone pubblica su RabbitMQ un evento CADF per ogni login.
# L'opt_out predefinito escluderebbe i login riusciti: resta solo "pending"
function configure_keystone_notifications {
    iniset $KEYSTONE_CONF oslo_messaging_notifications driver messagingv2
    iniset $KEYSTONE_CONF oslo_messaging_notifications transport_url "$(get_notification_url)"
    iniset $KEYSTONE_CONF DEFAULT notification_format cadf
    iniset $KEYSTONE_CONF DEFAULT notification_opt_out identity.authenticate.pending
    $SYSTEMCTL restart devstack@keystone.service
    wait_for_service $SERVICE_TIMEOUT $KEYSTONE_SERVICE_URI
}

# Crea in Keystone: Utente di servizio (admin), progetto delle esche e servizio
# "deception" nel catalogo, da cui Horizon e la CLI trovano le API
function create_honeystack_accounts {
    create_service_user $HONEYSTACK_SERVICE_USER admin
    get_or_create_project $HONEYSTACK_DECOY_PROJECT default
    get_or_create_service honey-stack deception "Honey-Stack: honeytoken per Keystone"
    get_or_create_endpoint deception "$REGION_NAME" \
        "$SERVICE_PROTOCOL://$SERVICE_HOST:$HONEYSTACK_PORT"
}

# Un nuovo stack.sh ricrea Keystone: le esche vecchie non esistono piu'.
# Il vecchio database va in honey-stack.<data>, si riparte vuoti
function archive_honeystack_data {
    if [[ -e $HONEYSTACK_DATA_DIR ]]; then
        mv $HONEYSTACK_DATA_DIR "$HONEYSTACK_DATA_DIR.$(date +%Y%m%d-%H%M%S)"
    fi
    mkdir -p $HONEYSTACK_DATA_DIR
}

# Scrive /etc/honey-stack/honey-stack.conf (cartella 700, file 600:
# contiene la password dell'utente di servizio)
function configure_honeystack {
    sudo install -d -o $STACK_USER -g $STACK_USER -m 700 $HONEYSTACK_CONF_DIR
    install -m 600 $HONEYSTACK_DIR/etc/honey-stack.conf.sample $HONEYSTACK_CONF
    iniset $HONEYSTACK_CONF DEFAULT db_path $HONEYSTACK_DATA_DIR/honeystack.db
    iniset $HONEYSTACK_CONF DEFAULT decoy_dir $HONEYSTACK_DATA_DIR/esche
    iniset $HONEYSTACK_CONF DEFAULT decoy_project $HONEYSTACK_DECOY_PROJECT
    iniset $HONEYSTACK_CONF DEFAULT dashboard_port $HONEYSTACK_PORT
    iniset $HONEYSTACK_CONF DEFAULT keystone_conf $KEYSTONE_CONF
    iniset $HONEYSTACK_CONF service_user auth_url $KEYSTONE_SERVICE_URI
    iniset $HONEYSTACK_CONF service_user username $HONEYSTACK_SERVICE_USER
    # la password non deve comparire nel log di stack.sh
    local xtrace
    xtrace=$(set +o | grep xtrace)
    set +o xtrace
    iniset $HONEYSTACK_CONF service_user password $SERVICE_PASSWORD
    $xtrace
    iniset $HONEYSTACK_CONF service_user project_name $SERVICE_PROJECT_NAME
    iniset $HONEYSTACK_CONF service_user user_domain_name $SERVICE_DOMAIN_NAME
    iniset $HONEYSTACK_CONF service_user project_domain_name $SERVICE_DOMAIN_NAME
}

# Pannelli in Horizon (Admin -> Honey-Stack): i file "enabled" vanno
# copiati in post-config, prima che DevStack prepari Horizon e Apache
function configure_honeystack_horizon {
    cp $HONEYSTACK_DIR/honeystack_dashboard/enabled/_9*_honeystack_*.py \
        $HORIZON_DIR/openstack_dashboard/local/enabled/
}

# ==================================================================
# FASE "stack extra" (./stack.sh): avvio dei servizi
# ==================================================================

# Avvia watcher e API come servizi systemd di DevStack
function start_honeystack {
    local bin_dir
    bin_dir=$(get_python_exec_prefix)
    run_process honey-stack-watcher "$bin_dir/honey-stack-watcher"
    run_process honey-stack-dashboard "$bin_dir/honey-stack-dashboard"
}

# ==================================================================
# MODALITA' "unstack" (./unstack.sh): arresto dei servizi
# ==================================================================

# Ferma i due servizi (unstack.sh)
function stop_honeystack {
    stop_process honey-stack-watcher
    stop_process honey-stack-dashboard
}

# ==================================================================
# MODALITA' "clean" (./clean.sh): pulizia
# ==================================================================

# Toglie i pannelli da Horizon
function cleanup_honeystack_horizon {
    rm -f $HORIZON_DIR/openstack_dashboard/local/enabled/_9*_honeystack_*.py
}

# clean.sh: toglie configurazione e pannelli messi fuori da /opt/stack
function cleanup_honeystack {
    sudo rm -rf $HONEYSTACK_CONF_DIR
    if is_service_enabled horizon; then
        cleanup_honeystack_horizon
    fi
}

# ==================================================================
# SMISTAMENTO: cosa eseguire in ogni modalita' e fase
# ==================================================================

# DevStack chiama questo file con modalita' (stack, unstack, clean) e fase
if is_service_enabled honey-stack-watcher honey-stack-dashboard; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installazione di Honey-Stack"
        install_honeystack
    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        echo_summary "Configurazione di Honey-Stack"
        configure_keystone_notifications
        create_honeystack_accounts
        archive_honeystack_data
        configure_honeystack
        if is_service_enabled horizon; then
            configure_honeystack_horizon
        fi
    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        echo_summary "Avvio di Honey-Stack"
        start_honeystack
    fi

    if [[ "$1" == "unstack" ]]; then
        stop_honeystack
    fi

    if [[ "$1" == "clean" ]]; then
        cleanup_honeystack
    fi
fi
