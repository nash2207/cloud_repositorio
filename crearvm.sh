#!/bin/bash
VM_NAME=$1
OVS_NAME=$2
VNC_PORT=$3
VLAN_A=$4
VLAN_B=$5 # Puede estar vacío si es un nodo final de una línea

BASE_IMG="cirros-0.5.1-x86_64-disk.img"
VM_IMG="${VM_NAME}_img.qcow2"
TAP_A="${VM_NAME}_tapA"
MAC_A="20:17:68:15:$(printf '%02x' $VLAN_A):$(printf '%02x' $((VNC_PORT % 100)))"

echo "  -> [Nodo Local] Configurando VM $VM_NAME..."

# 1. Preparar disco
[ -f $BASE_IMG ] || wget -q http://download.cirros-cloud.net/0.5.1/cirros-0.5.1-x86_64-disk.img
qemu-img create -f qcow2 -b $BASE_IMG -F qcow2 $VM_IMG > /dev/null

# 2. Configurar Interfaz 1 (Hacia el vecino A)
sudo ip tuntap add mode tap name $TAP_A 2>/dev/null
sudo ip link set dev $TAP_A up
sudo ovs-vsctl --may-exist add-port $OVS_NAME $TAP_A tag=$VLAN_A

# 3. Construir comando base de QEMU
QEMU_CMD="sudo qemu-system-x86_64 -enable-kvm -vnc 0.0.0.0:$VNC_PORT -daemonize -drive file=$VM_IMG,format=qcow2"
QEMU_CMD+=" -netdev tap,id=netA,ifname=$TAP_A,script=no,downscript=no -device e1000,netdev=netA,mac=$MAC_A"

# 4. Configurar Interfaz 2 (Hacia el vecino B) SI EXISTE
if [ ! -z "$VLAN_B" ]; then
    TAP_B="${VM_NAME}_tapB"
    MAC_B="20:17:68:15:$(printf '%02x' $VLAN_B):$(printf '%02x' $((VNC_PORT % 100)))"
    
    sudo ip tuntap add mode tap name $TAP_B 2>/dev/null
    sudo ip link set dev $TAP_B up
    sudo ovs-vsctl --may-exist add-port $OVS_NAME $TAP_B tag=$VLAN_B
    
    QEMU_CMD+=" -netdev tap,id=netB,ifname=$TAP_B,script=no,downscript=no -device e1000,netdev=netB,mac=$MAC_B"
fi

# 5. Levantar la VM
eval $QEMU_CMD
echo "  -> [Nodo Local] VM $VM_NAME encendida (VNC: $VNC_PORT)."