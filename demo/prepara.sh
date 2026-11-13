#!/bin/bash
# demo/prepara.sh - prepara la DevStack per la demo di Honey-Stack.
#
# Da eseguire sulla DevStack come utente stack, dopo l'avvio della VM:
#   demo/prepara.sh
#
# Rimette in ordine cio' che un riavvio della DevStack lascia indietro:
#   1. indirizzo di br-ex, senza il quale floating IP e SSH verso le VM
#      non funzionano;
#   2. servizi di Honey-Stack (watcher e dashboard);
#   3. VM con l'esca (predefinita web-01): accesa se e' spenta, rilasciata
#      se e' rimasta in quarantena da una demo precedente;
# e alla fine mostra le esche attive.

set -u

VM=${DEMO_VM:-web-01}
HONEY_STACK=${HONEY_STACK:-/opt/stack/data/venv/bin/honey-stack}
OPENRC=${OPENRC:-/opt/stack/devstack/openrc}

if [[ -t 1 ]]; then
    B=$'\e[1m'; GREEN=$'\e[32m'; RED=$'\e[31m'; CYAN=$'\e[36m'; R=$'\e[0m'
else
    B=; GREEN=; RED=; CYAN=; R=
fi
title() { echo; echo "${B}${CYAN}=== $* ===${R}"; }
ok()    { echo "  ${GREEN}$*${R}"; }
ko()    { echo "  ${RED}$*${R}"; }
die()   { echo "${RED}Errore: $*${R}" >&2; exit 1; }

[[ $(id -un) == stack ]] || die "va eseguito come utente stack (sudo -u stack -i)"
[[ -x $HONEY_STACK ]] || die "comando honey-stack non trovato in $HONEY_STACK"
# openrc usa variabili non definite: set -u va sospeso mentre lo si carica
set +u
# shellcheck disable=SC1090
source "$OPENRC" admin admin > /dev/null 2>&1 || die "impossibile caricare $OPENRC"
set -u

title "Rete"
if ping -c 1 -W 3 8.8.8.8 > /dev/null 2>&1; then
    ok "Rete verso l'esterno funzionante"
else
    ko "Nessuna rete verso l'esterno: su Windows controlla 'VMware NAT Service'"
fi
sudo ip link set br-ex up
sudo ip addr replace 172.24.4.1/24 dev br-ex
ok "br-ex: $(ip -4 -o addr show br-ex | awk '{print $4}')"

title "Servizi di Honey-Stack"
for s in devstack@honey-stack-watcher devstack@honey-stack-dashboard; do
    if ! systemctl is-active --quiet "$s"; then
        echo "  $s non attivo: lo riavvio"
        sudo systemctl restart "$s"
        sleep 3
    fi
    if systemctl is-active --quiet "$s"; then ok "$s attivo"; else ko "$s NON attivo"; fi
done

title "VM con l'esca ($VM)"
riga=$(openstack server list --all-projects --name "^$VM\$" -f value -c ID -c Status | head -1)
[[ -n $riga ]] || die "la VM $VM non esiste: creala con 'honey-stack create-vm ESCA $VM'"
id=${riga%% *}
stato=${riga##* }
echo "  ID $id, stato $stato"
if [[ $stato == SHUTOFF ]]; then
    echo "  La accendo..."
    openstack server start "$id"
fi
for _ in $(seq 1 30); do
    stato=$(openstack server show "$id" -f value -c status)
    [[ $stato == ACTIVE ]] && break
    sleep 2
done
if [[ $stato == ACTIVE ]]; then ok "$VM ACTIVE"; else die "$VM e' in stato $stato"; fi

if "$HONEY_STACK" quarantine-list | grep -q "^$VM "; then
    echo "  $VM e' ancora in quarantena da una demo precedente: la rilascio"
    "$HONEY_STACK" release "$VM"
fi

ip_vm=$(openstack server show "$id" -f value -c addresses | grep -oE '172\.24\.4\.[0-9]+' | head -1)
if [[ -n $ip_vm ]]; then
    echo "  Floating IP $ip_vm: attendo che risponda (CirrOS impiega circa un minuto ad avviarsi)..."
    for _ in $(seq 1 60); do
        ping -c 1 -W 2 "$ip_vm" > /dev/null 2>&1 && break
        sleep 2
    done
    if ping -c 1 -W 2 "$ip_vm" > /dev/null 2>&1; then ok "$VM risponde su $ip_vm"; else ko "$VM non risponde su $ip_vm"; fi
else
    ko "$VM non ha un floating IP"
fi

title "Esche attive"
"$HONEY_STACK" list

echo
echo "${B}DevStack pronta. Su Kali: demo/demo.sh check${R}"
