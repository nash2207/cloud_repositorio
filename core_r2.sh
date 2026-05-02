#!/bin/bash

COMPUTE1="10.0.10.1"
COMPUTE2="10.0.10.2"
OVS_NAME="br-int"

deploy_linear() {
    echo "================================================="
    echo " INICIANDO TOPOLOGÍA LINEAL (3 VMs) "
    echo "================================================="
    echo "Estructura Lógica: VM1(H1) <VLAN 101> VM2(H2) <VLAN 102> VM3(H1)"
    
    # VM1: Solo se conecta a VM2 (VLAN 101). Parámetro 5 vacío ("").
    echo "[+] Desplegando VM1 en $COMPUTE1..."
    ssh ubuntu@$COMPUTE1 'bash -s' < ./crearvm.sh "VM1_Lineal" "$OVS_NAME" 5911 "101" "" &
    
    # VM2: Está en el medio. Se conecta a VM1 (VLAN 101) y a VM3 (VLAN 102).
    echo "[+] Desplegando VM2 en $COMPUTE2..."
    ssh ubuntu@$COMPUTE2 'bash -s' < ./crearvm.sh "VM2_Lineal" "$OVS_NAME" 5912 "101" "102" &
    
    # VM3: Solo se conecta a VM2 (VLAN 102). Parámetro 5 vacío ("").
    echo "[+] Desplegando VM3 en $COMPUTE1..."
    ssh ubuntu@$COMPUTE1 'bash -s' < ./crearvm.sh "VM3_Lineal" "$OVS_NAME" 5913 "102" "" &
    
    wait
    echo "Topología Lineal desplegada."
}

deploy_ring() {
    echo "================================================="
    echo " INICIANDO TOPOLOGÍA ANILLO (4 VMs) "
    echo "================================================="
    echo "Enlaces: VM1-VM2 (201), VM2-VM3 (202), VM3-VM4 (203), VM4-VM1 (204)"
    
    # En un anillo, TODOS los nodos tienen exactamente 2 interfaces (vecino izquierdo y derecho)
    
    echo "[+] Desplegando VM1 en $COMPUTE1..."
    ssh ubuntu@$COMPUTE1 'bash -s' < ./crearvm.sh "VM1_Anillo" "$OVS_NAME" 5921 "201" "204" &
    
    echo "[+] Desplegando VM2 en $COMPUTE2..."
    ssh ubuntu@$COMPUTE2 'bash -s' < ./crearvm.sh "VM2_Anillo" "$OVS_NAME" 5922 "201" "202" &
    
    echo "[+] Desplegando VM3 en $COMPUTE1..."
    ssh ubuntu@$COMPUTE1 'bash -s' < ./crearvm.sh "VM3_Anillo" "$OVS_NAME" 5923 "202" "203" &
    
    echo "[+] Desplegando VM4 en $COMPUTE2..."
    ssh ubuntu@$COMPUTE2 'bash -s' < ./crearvm.sh "VM4_Anillo" "$OVS_NAME" 5924 "203" "204" &
    
    wait
    echo "Topología Anillo desplegada."
}

# --- MENÚ ---
echo "Seleccione la topología a desplegar:"
echo "1) Lineal (3 VMs, Enlaces P2P)"
echo "2) Anillo (4 VMs, Enlaces P2P)"
read -p "Opción: " OPCION

case $OPCION in
    1) deploy_linear ;;
    2) deploy_ring ;;
    *) echo "Opción no válida."; exit 1 ;;
esac