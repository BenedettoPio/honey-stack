#!/bin/bash
# Plugin DevStack di Honey-Stack.
# Si attiva in local.conf con:
#   enable_plugin honey-stack https://github.com/BenedettoPio/honey-stack main

function install_honeystack {
    setup_develop $HONEYSTACK_DIR
}

# Notifiche CADF di Keystone su RabbitMQ, anche per i login riusciti
function configure_keystone_notifications {
    iniset $KEYSTONE_CONF oslo_messaging_notifications driver messagingv2
    iniset $KEYSTONE_CONF oslo_messaging_notifications transport_url "$(get_notification_url)"
    iniset $KEYSTONE_CONF DEFAULT notification_format cadf
    iniset $KEYSTONE_CONF DEFAULT notification_opt_out identity.authenticate.pending
    $SYSTEMCTL restart devstack@keystone.service
    wait_for_service $SERVICE_TIMEOUT $KEYSTONE_SERVICE_URI
}

# Utente di servizio, progetto delle esche e servizio nel catalogo
function create_honeystack_accounts {
    create_service_user $HONEYSTACK_SERVICE_USER admin
    get_or_create_project $HONEYSTACK_DECOY_PROJECT default
    get_or_create_service honey-stack deception "Honey-Stack: honeytoken per Keystone"
    get_or_create_endpoint deception "$REGION_NAME" \
        "$SERVICE_PROTOCOL://$SERVICE_HOST:$HONEYSTACK_PORT"
}

# Un nuovo stack.sh azzera Keystone: database ed esche vecchi
# non valgono piu' e vengono messi da parte con la data
function archive_honeystack_data {
    if [[ -e $HONEYSTACK_DATA_DIR ]]; then
        mv $HONEYSTACK_DATA_DIR "$HONEYSTACK_DATA_DIR.$(date +%Y%m%d-%H%M%S)"
    fi
    mkdir -p $HONEYSTACK_DATA_DIR
}

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

function start_honeystack {
    local bin_dir
    bin_dir=$(get_python_exec_prefix)
    run_process honey-stack-watcher "$bin_dir/honey-stack-watcher"
    run_process honey-stack-dashboard "$bin_dir/honey-stack-dashboard"
}

function stop_honeystack {
    stop_process honey-stack-watcher
    stop_process honey-stack-dashboard
}

function cleanup_honeystack {
    sudo rm -rf $HONEYSTACK_CONF_DIR
}

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
