#include <stdio.h>
#include <string.h>
#include <windows.h>

#include "mil1553api.h"
#include "mil1553defs.h"
#include "mil1553types.h"

static int check_ret(const char *step, ZUINT32 ret)
{
    if (ret == RET_SUCCESS) {
        printf("%s ok\n", step);
        return 0;
    }
    printf("%s failed: ret=0x%08x\n", step, ret);
    return 1;
}

static void print_cdp(const char *prefix, const MIL_1553CDP_STRUCT *cdp)
{
    printf("%s CDP_STS=0x%08x CMD1=0x%04x RT_STS1=0x%08x DATA0=0x%04x DATA31=0x%04x\n",
           prefix,
           cdp->CDP_STS,
           cdp->CMD1 & 0xffffu,
           cdp->Rt_Sts1,
           cdp->Msg_Data[0] & 0xffffu,
           cdp->Msg_Data[31] & 0xffffu);
}

int main(int argc, char **argv)
{
    ZUINT8 card_index = 0;
    ZUINT8 channel = 0;
    ZHANDLE handle = -1;
    ZUINT32 ret = RET_SUCCESS;

    if (argc > 1) {
        card_index = (ZUINT8)strtoul(argv[1], NULL, 0);
    }
    if (argc > 2) {
        channel = (ZUINT8)strtoul(argv[2], NULL, 0);
    }

    printf("Self test: BC -> RT1/SA1 with BM monitor, card=%u channel=%u\n",
           card_index,
           channel);

    ret = MIL1553_DeviceOpen(&handle, card_index);
    if (check_ret("DeviceOpen", ret)) {
        return 1;
    }

    ret = MIL1553_DeviceReset(handle, channel);
    if (check_ret("DeviceReset", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    ZUINT8 channel_count = 0;
    ZUINT8 mult_nsingle = 0;
    ZUINT8 vol_regulate_en = 0;
    ZUINT8 err_inject_en = 0;
    ZUINT8 bps_change_en = 0;
    ZUINT32 seq_number = 0;
    ret = MIL1553_GetInfo(handle,
                          &channel_count,
                          &mult_nsingle,
                          &vol_regulate_en,
                          &err_inject_en,
                          &bps_change_en,
                          &seq_number);
    if (ret == RET_SUCCESS) {
        printf("GetInfo: channel_count=%u mult_nsingle=%u err_inject=%u bps_change=%u seq=%u\n",
               channel_count,
               mult_nsingle,
               err_inject_en,
               bps_change_en,
               seq_number);
    } else {
        printf("GetInfo failed: ret=0x%08x\n", ret);
    }

    ret = MIL1553_RTInit(handle, channel);
    if (check_ret("RTInit", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    ret = MIL1553_RT_Cdp_Allocate(handle, channel, 1, 1, 0, 16);
    if (check_ret("RT_Cdp_Allocate RT1 SA1 RX", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    ret = MIL1553_RT_Addr_Enable(handle, channel, 1);
    if (check_ret("RT_Addr_Enable RT1", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    ret = MIL1553_RT_MODE_Enable(handle, channel);
    if (check_ret("RT_MODE_Enable", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    ret = MIL1553_BMInit(handle, channel, 2048);
    if (check_ret("BMInit", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    for (ZUINT8 rt_addr = 0; rt_addr < 32; ++rt_addr) {
        for (ZUINT8 subaddr = 0; subaddr < 32; ++subaddr) {
            MIL1553_BMSetFilter(handle, channel, rt_addr, subaddr, TRUE);
        }
    }

    ret = MIL1553_BM_MODE_Enable(handle, channel);
    if (check_ret("BM_MODE_Enable", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    ret = MIL1553_BC_MODE_Enable(handle, channel);
    if (check_ret("BC_MODE_Enable", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    ret = MIL1553_BCInit(handle, channel, 16, 0);
    if (check_ret("BCInit", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    MIL_1553BCCB_STRUCT bccb;
    memset(&bccb, 0, sizeof(bccb));
    bccb.BCMSG_DELAY_TIME = 1000;
    ret = MIL1553_BCCB_Write(handle, channel, 0, &bccb);
    if (check_ret("BCCB_Write", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    MIL_1553CDP_STRUCT bc_cdp;
    memset(&bc_cdp, 0, sizeof(bc_cdp));
    ret = MIL1553_GetCmdWord(1, 0, 1, 0, &bc_cdp.CMD1);
    if (check_ret("GetCmdWord RT1 RX SA1 WC32", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }
    bc_cdp.CUR_MSG_NUM = 0;
    bc_cdp.NEXT_MSG_NUM = NO_NEXT;
    for (ZUINT32 i = 0; i < 32; ++i) {
        bc_cdp.Msg_Data[i] = 0x3300u + i;
    }

    ret = MIL1553_BCCDP_Write(handle, channel, 0, &bc_cdp);
    if (check_ret("BCCDP_Write", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    Sleep(100);

    ret = MIL1553_BCStart(handle, channel, 0);
    if (check_ret("BCStart", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    for (int i = 0; i < 3000; ++i) {
        ZUINT32 is_running = 0;
        ret = MIL1553_BCIsRunning(handle, channel, &is_running);
        if (ret != RET_SUCCESS) {
            printf("BCIsRunning failed: ret=0x%08x\n", ret);
            MIL1553_DeviceClose(handle);
            return 1;
        }
        if (is_running == 0) {
            break;
        }
        Sleep(1);
    }

    MIL_1553CDP_STRUCT bc_readback;
    memset(&bc_readback, 0, sizeof(bc_readback));
    ret = MIL1553_BCCDP_Read(handle, channel, 0, &bc_readback);
    if (ret == RET_SUCCESS) {
        print_cdp("BC readback", &bc_readback);
    } else {
        printf("BCCDP_Read failed: ret=0x%08x\n", ret);
    }

    MIL_1553CDP_STRUCT rt_readback;
    memset(&rt_readback, 0, sizeof(rt_readback));
    ret = MIL1553_RTCDP_Read(handle, channel, 1, 1, 0, 0, &rt_readback);
    if (ret == RET_SUCCESS) {
        print_cdp("RT readback", &rt_readback);
    } else {
        printf("RTCDP_Read failed: ret=0x%08x\n", ret);
    }

    int bm_seen = 0;
    for (int poll = 0; poll < 100; ++poll) {
        MIL_1553CDP_STRUCT bm_cdp[32];
        ZUINT32 msg_cnt = 0;
        memset(bm_cdp, 0, sizeof(bm_cdp));
        ret = MIL1553_BMReadNewMsgs(handle, channel, bm_cdp, &msg_cnt);
        if (ret == RET_SUCCESS && msg_cnt > 0) {
            for (ZUINT32 i = 0; i < msg_cnt && i < 32; ++i) {
                print_cdp("BM seen", &bm_cdp[i]);
                bm_seen = 1;
            }
            break;
        }
        Sleep(10);
    }

    if (!bm_seen) {
        printf("BM did not report this message inside this process.\n");
        printf("If BC readback is OK but BM is empty, the card may not support BC+BM simultaneous mode on this channel.\n");
    }

    MIL1553_BCStop(handle, channel);
    MIL1553_BC_MODE_Disable(handle, channel);
    MIL1553_BM_MODE_Disable(handle, channel);
    MIL1553_RT_MODE_Disable(handle, channel);
    MIL1553_RT_Addr_Disable(handle, channel, 1);
    MIL1553_DeviceClose(handle);
    return bm_seen ? 0 : 2;
}
