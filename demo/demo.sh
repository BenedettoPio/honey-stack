#!/bin/bash
# demo/demo.sh - demo di Honey-Stack dal punto di vista dell'attaccante.
#
# Da eseguire sulla VM Kali (l'attaccante), non sulla DevStack: cosi' negli
# allarmi compare l'indirizzo di chi attacca. La dashboard di Honey-Stack
# (http://<devstack>:5050) va tenuta aperta accanto, per vedere gli allarmi.
#
# Comandi:
#   demo/demo.sh check                 controlli prima della demo
#   demo/demo.sh scenario1 [FILE]      credenziali rubate usate dall'esterno
#                                      (FILE = clouds.yaml esca rubato,
#                                      predefinito ~/Downloads/clouds.yaml)
#   demo/demo.sh scenario2             istanza compromessa: esca trovata
#                                      dentro la VM, quarantena e rilascio
#   demo/demo.sh all [FILE]            check, scenario 1 e scenario 2
#
# Opzione: --no-pause (prima del comando) non aspetta Invio tra un passo
# e l'altro. Il rilascio della VM dalla dashboard viene sempre atteso.
#
# Le variabili DEMO_* si possono cambiare da fuori, ad esempio:
#   DEMO_VM_IP=172.24.4.200 demo/demo.sh scenario2

set -u

DEVSTACK=${DEMO_DEVSTACK:-192.168.206.131}
DASHBOARD=${DEMO_DASHBOARD:-http://$DEVSTACK:5050}
PUBLIC_NET=${DEMO_PUBLIC_NET:-172.24.4.0/24}
VM_IP=${DEMO_VM_IP:-172.24.4.124}
VM_USER=${DEMO_VM_USER:-cirros}
VM_PASSWORD=${DEMO_VM_PASSWORD:-gocubsgo}
BRUTE_FORCE=${DEMO_BRUTE_FORCE:-5}
PAUSE=1

# --- Aspetto e funzioni di base ---------------------------------------------

if [[ -t 1 ]]; then
    B=$'\e[1m'; DIM=$'\e[2m'; GREEN=$'\e[32m'; RED=$'\e[31m'
    YELLOW=$'\e[33m'; CYAN=$'\e[36m'; R=$'\e[0m'
else
    B=; DIM=; GREEN=; RED=; YELLOW=; CYAN=; R=
fi

title() { echo; echo "${B}${CYAN}=== $* ===${R}"; }
step()  { echo; echo "${B}--- $* ---${R}"; }
say()   { echo "${DIM}$*${R}"; }
# Cosa guardare nella dashboard dopo il passo
look()  { echo "${YELLOW}Dashboard: $*${R}"; }
ok()    { echo "  ${GREEN}$*${R}"; }
ko()    { echo "  ${RED}$*${R}"; }
# Mostra il comando e poi lo esegue
show()  { echo "${B}\$ $*${R}"; eval "$*"; }
pause() { [[ $PAUSE == 1 ]] && read -r -p "${DIM}[Invio per continuare]${R}" _; return 0; }
die()   { echo "${RED}Errore: $*${R}" >&2; exit 1; }

# --- Funzioni di supporto -----------------------------------------------------

# Un campo del clouds.yaml (auth_url, username, password, project_name)
campo() { awk -v k="$2:" '$1 == k {print $2; exit}' "$1"; }

# Tentativo di accesso a Keystone con utente e password; stampa il codice
# HTTP (201 = password giusta, 401 = sbagliata)
accesso() {   # accesso <auth_url> <utente> <password>
    curl -s -o /dev/null -w "%{http_code}" -H "Content-Type: application/json" \
        -d "{\"auth\":{\"identity\":{\"methods\":[\"password\"],\"password\":{\"user\":{\"name\":\"$2\",\"domain\":{\"id\":\"default\"},\"password\":\"$3\"}}}}}" \
        "$1/v3/auth/tokens"
}

# Esegue un comando dentro la VM, via SSH sul floating IP
vmssh() {
    sshpass -p "$VM_PASSWORD" ssh -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=5 \
        "$VM_USER@$VM_IP" "$@"
}

raggiungibile() { ping -c 1 -W 2 "$VM_IP" > /dev/null 2>&1; }

# --- check --------------------------------------------------------------------

cmd_check() {
    local errori=0 codice
    title "Controlli prima della demo"

    if curl -s -o /dev/null --max-time 5 "http://$DEVSTACK/identity/v3"; then
        ok "Keystone raggiungibile (http://$DEVSTACK/identity)"
    else
        ko "Keystone NON raggiungibile: la DevStack e' accesa? Su Windows il servizio 'VMware NAT Service' e' in esecuzione?"
        errori=$((errori + 1))
    fi

    codice=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$DASHBOARD/login")
    if [[ $codice == 200 ]]; then
        ok "Dashboard di Honey-Stack raggiungibile ($DASHBOARD)"
    else
        ko "Dashboard NON raggiungibile ($DASHBOARD, codice $codice)"
        errori=$((errori + 1))
    fi

    if ip route get "$VM_IP" 2>/dev/null | grep -q "via $DEVSTACK"; then
        ok "Rotta verso le VM del cloud ($PUBLIC_NET via $DEVSTACK)"
    else
        say "Manca la rotta verso le VM del cloud: la aggiungo (sparisce al riavvio di Kali)"
        show "sudo ip route add $PUBLIC_NET via $DEVSTACK"
    fi

    if raggiungibile; then
        ok "VM con l'esca raggiungibile ($VM_IP)"
    else
        ko "VM $VM_IP NON raggiungibile: sulla DevStack lancia demo/prepara.sh (accende la VM e sistema br-ex)"
        errori=$((errori + 1))
    fi

    if command -v sshpass > /dev/null; then
        ok "sshpass presente"
    else
        say "Installo sshpass (serve per entrare nella VM CirrOS senza digitare la password)"
        sudo apt-get install -y sshpass > /dev/null || { ko "installazione di sshpass fallita"; errori=$((errori + 1)); }
    fi

    if command -v openstack > /dev/null; then
        ok "Client openstack presente (usato nello scenario 1)"
    else
        say "  Client openstack assente: lo scenario 1 usera' solo curl (facoltativo: pipx install python-openstackclient)"
    fi

    echo
    if (( errori == 0 )); then
        echo "${GREEN}${B}Tutto pronto per la demo.${R}"
    else
        echo "${RED}${B}$errori controlli non superati: sistemali prima di iniziare.${R}"
        return 1
    fi
}

# --- scenario 1 -----------------------------------------------------------------

cmd_scenario1() {
    local file=${1:-$HOME/Downloads/clouds.yaml}
    local url utente password codice i
    [[ -r $file ]] || die "file esca $file non trovato (scaricalo dalla dashboard: colonna 'File esca')"
    url=$(campo "$file" auth_url)
    utente=$(campo "$file" username)
    password=$(campo "$file" password)
    [[ -n $url && -n $utente && -n $password ]] || die "$file non sembra un clouds.yaml di OpenStack"

    title "Scenario 1: credenziali rubate usate dall'esterno"
    say "L'attaccante ha trovato un file clouds.yaml (su un PC, in un repository,"
    say "in un backup). Non sa che e' un'esca: sembra un accesso di servizio."
    pause

    step "1. Il file rubato"
    show "cat '$file'"
    say "Contiene indirizzo di Keystone, utente e password: tutto il necessario per entrare."
    pause

    step "2. Primo tentativo, con una password sbagliata"
    say "L'attaccante prova a indovinare (o ha una versione vecchia del file)."
    echo "${B}\$ curl ... $url/v3/auth/tokens  (utente $utente, password sbagliata)${R}"
    codice=$(accesso "$url" "$utente" "tentativo-1")
    echo "  risposta di Keystone: $codice"
    look "allarme ATTENZIONE su $utente, con l'IP di Kali e lo strumento curl"
    pause

    step "3. Brute force: altre $((BRUTE_FORCE - 1)) password sbagliate"
    say "Keystone pubblica un evento CADF per ogni tentativo; Honey-Stack correla"
    say "gli allarmi dallo stesso IP: $BRUTE_FORCE password sbagliate in 5 minuti = brute force."
    for (( i = 2; i <= BRUTE_FORCE; i++ )); do
        codice=$(accesso "$url" "$utente" "tentativo-$i")
        echo "  tentativo $i: $codice"
    done
    look "allarme GRAVE di brute force ('$BRUTE_FORCE password sbagliate')"
    pause

    step "4. Accesso con la password giusta del file"
    say "Ora l'attaccante usa la password vera: chi la conosce ha letto il file esca."
    echo "${B}\$ curl ... $url/v3/auth/tokens  (utente $utente, password del file)${R}"
    codice=$(accesso "$url" "$utente" "$password")
    echo "  risposta di Keystone: $codice"
    look "allarme GRAVE su $utente: le credenziali sono state rubate"
    pause

    if command -v openstack > /dev/null; then
        step "5. Lo stesso file con il client ufficiale di OpenStack"
        say "Un attaccante reale userebbe il client openstack con il file rubato."
        show "OS_CLIENT_CONFIG_FILE='$file' openstack --os-cloud openstack project list"
        say "Il client risponde con un errore: l'esca non ha ruoli e non apre nulla."
        say "Ma la password era giusta, quindi Honey-Stack segnala un accesso riuscito."
        look "un altro allarme GRAVE su $utente, con lo strumento del client al posto di curl"
        pause
    fi
}

# --- scenario 2 -------------------------------------------------------------------

cmd_scenario2() {
    local t
    command -v sshpass > /dev/null || die "manca sshpass: lancia prima 'demo/demo.sh check'"
    raggiungibile || die "la VM $VM_IP non risponde: lancia prima 'demo/demo.sh check'"

    title "Scenario 2: un'istanza del cloud compromessa"
    say "L'attaccante e' riuscito a entrare in una VM del cloud ($VM_IP)."
    say "Honey-Stack, alla creazione della VM, vi ha lasciato un'esca dove gli"
    say "strumenti OpenStack cercano le credenziali."
    pause

    step "1. L'attaccante entra nella VM e si guarda intorno"
    show "vmssh hostname"
    show "vmssh ls -l .config/openstack/"
    show "vmssh cat .config/openstack/clouds.yaml"
    say "Credenziali di OpenStack dentro la VM: l'attaccante prova a usarle."
    pause

    step "2. Dalla VM, l'attaccante usa le credenziali trovate"
    echo "${B}\$ vmssh  (dentro la VM: legge utente e password dal file e chiama Keystone con curl)${R}"
    vmssh sh -s <<'EOF'
F=~/.config/openstack/clouds.yaml
URL=$(awk '$1 == "auth_url:" {print $2}' "$F")
U=$(awk '$1 == "username:" {print $2}' "$F")
P=$(awk '$1 == "password:" {print $2}' "$F")
echo "  risposta di Keystone: $(curl -s -o /dev/null -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d "{\"auth\":{\"identity\":{\"methods\":[\"password\"],\"password\":{\"user\":{\"name\":\"$U\",\"domain\":{\"id\":\"default\"},\"password\":\"$P\"}}}}}" \
  "$URL/v3/auth/tokens")"
EOF
    say "Keystone vede come origine il floating IP della VM ($VM_IP)."
    look "allarme GRAVE con il nome della VM nel luogo dell'esca e strumento curl/7.84.0 (il curl di CirrOS)"
    pause

    step "3. La quarantena automatica"
    say "Honey-Stack trova tramite Neutron la porta della VM e le toglie i security"
    say "group, sostituendoli con uno senza regole: tutto il traffico e' bloccato."
    for t in 1 2 3 4 5 6 7 8 9 10; do
        raggiungibile || break
        sleep 1
    done
    show "ping -c 3 -W 1 $VM_IP"
    show "vmssh hostname || echo '  connessione SSH fallita: la VM è isolata'"
    look "sezione 'VM in quarantena (1)' con il pulsante Rilascia, e l'allarme GRAVE 'quarantena'"
    pause

    step "4. Il rilascio, deciso dall'operatore"
    say "La VM resta accesa per l'analisi. Quando l'operatore ha controllato, la rilascia:"
    look "premi 'Rilascia' accanto alla VM, nella sezione 'VM in quarantena'"
    echo "${DIM}In attesa del rilascio (al massimo 5 minuti)...${R}"
    for (( t = 0; t < 300; t += 3 )); do
        raggiungibile && break
        sleep 3
    done
    raggiungibile || die "la VM non e' stata rilasciata entro 5 minuti"
    ok "La VM risponde di nuovo"
    show "vmssh hostname"
    say "I security group originali sono stati ripristinati."
}

# --- Comando ------------------------------------------------------------------------

if [[ ${1:-} == --no-pause ]]; then
    PAUSE=0
    shift
fi

case "${1:-}" in
    check)     cmd_check ;;
    scenario1) cmd_scenario1 "${2:-}" ;;
    scenario2) cmd_scenario2 ;;
    all)       cmd_check && cmd_scenario1 "${2:-}" && cmd_scenario2 ;;
    *)         sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
