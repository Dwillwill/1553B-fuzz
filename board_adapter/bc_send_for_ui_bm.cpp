#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#include "mil1553api.h"
#include "mil1553defs.h"
#include "mil1553types.h"

static int check_ret(const char *step, ZUINT32 ret)
{
    if (ret == RET_SUCCESS) {
        return 0;
    }
    printf("%s failed: ret=0x%08x\n", step, ret);
    return 1;
}

static void usage(const char *program)
{
    printf("Usage: %s [card] [channel] [rt] [sa] [repeat] [interval_ms] [bus]\n", program);
    printf("Defaults: card=0 channel=0 rt=1 sa=1 repeat=10 interval_ms=1000 bus=A\n");
    printf("Example:  %s 0 0 1 1 10 1000 A\n", program);
}

int main(int argc, char **argv)
{
    ZUINT8 card = 0;
    ZUINT8 channel = 0;
    ZUINT8 rt = 1;
    ZUINT8 sa = 1;
    unsigned int repeat = 10;
    unsigned int interval_ms = 1000;
    int send_from_bus_b = 0;
    ZHANDLE handle = -1;

    if (argc > 1) {
        card = (ZUINT8)strtoul(argv[1], NULL, 0);
    }
    if (argc > 2) {
        channel = (ZUINT8)strtoul(argv[2], NULL, 0);
    }
    if (argc > 3) {
        rt = (ZUINT8)strtoul(argv[3], NULL, 0);
    }
    if (argc > 4) {
        sa = (ZUINT8)strtoul(argv[4], NULL, 0);
    }
    if (argc > 5) {
        repeat = (unsigned int)strtoul(argv[5], NULL, 0);
    }
    if (argc > 6) {
        interval_ms = (unsigned int)strtoul(argv[6], NULL, 0);
    }
    if (argc > 7) {
        send_from_bus_b = (argv[7][0] == 'B' || argv[7][0] == 'b');
    }
    if (argc > 8) {
        usage(argv[0]);
        return 2;
    }

    printf("BC sender for UI BM: card=%u channel=%u rt=%u sa=%u repeat=%u interval_ms=%u bus=%c\n",
           card,
           channel,
           rt,
           sa,
           repeat,
           interval_ms,
           send_from_bus_b ? 'B' : 'A');
    printf("This demo does NOT call DeviceReset, RTInit, BMInit, or BM_MODE_Enable.\n");

    ZUINT32 ret = MIL1553_DeviceOpen(&handle, card);
    if (check_ret("DeviceOpen", ret)) {
        return 1;
    }

    ret = MIL1553_BC_MODE_Enable(handle, channel);
    if (check_ret("BC_MODE_Enable", ret)) {
        MIL1553_DeviceClose(handle);
        return 1;
    }

    ret = MIL1553_BCInit(handle, channel, 16, 0);
    if (check_ret("BCInit", ret)) {
        MIL1553_BC_MODE_Disable(handle, channel);
        MIL1553_DeviceClose(handle);
        return 1;
    }

    MIL_1553BCCB_STRUCT bccb;
    memset(&bccb, 0, sizeof(bccb));
    bccb.BCMSG_DELAY_TIME = 1000;
    if (send_from_bus_b) {
        bccb.BCMSG_FMT |= SEND_FROM_CHB;
    }

    ret = MIL1553_BCCB_Write(handle, channel, 0, &bccb);
    if (check_ret("BCCB_Write", ret)) {
        MIL1553_BC_MODE_Disable(handle, channel);
        MIL1553_DeviceClose(handle);
        return 1;
    }

    for (unsigned int n = 0; n < repeat; ++n) {
        MIL_1553CDP_STRUCT cdp;
        memset(&cdp, 0, sizeof(cdp));

        ret = MIL1553_GetCmdWord(rt, 0, sa, 0, &cdp.CMD1);
        if (check_ret("GetCmdWord", ret)) {
            MIL1553_BC_MODE_Disable(handle, channel);
            MIL1553_DeviceClose(handle);
            return 1;
        }

        cdp.CUR_MSG_NUM = 0;
        cdp.NEXT_MSG_NUM = NO_NEXT;
        for (ZUINT32 i = 0; i < 32; ++i) {
            cdp.Msg_Data[i] = 0x4400u + ((n & 0xffu) << 8) + i;
        }

        ret = MIL1553_BCCDP_Write(handle, channel, 0, &cdp);
        if (check_ret("BCCDP_Write", ret)) {
            MIL1553_BC_MODE_Disable(handle, channel);
            MIL1553_DeviceClose(handle);
            return 1;
        }

        ret = MIL1553_BCStart(handle, channel, 0);
        if (check_ret("BCStart", ret)) {
            MIL1553_BC_MODE_Disable(handle, channel);
            MIL1553_DeviceClose(handle);
            return 1;
        }

        for (unsigned int waited = 0; waited < 3000; ++waited) {
            ZUINT32 is_running = 0;
            ret = MIL1553_BCIsRunning(handle, channel, &is_running);
            if (ret != RET_SUCCESS) {
                printf("BCIsRunning failed: ret=0x%08x\n", ret);
                MIL1553_BCStop(handle, channel);
                MIL1553_BC_MODE_Disable(handle, channel);
                MIL1553_DeviceClose(handle);
                return 1;
            }
            if (is_running == 0) {
                break;
            }
            Sleep(1);
        }

        MIL_1553CDP_STRUCT readback;
        memset(&readback, 0, sizeof(readback));
        ret = MIL1553_BCCDP_Read(handle, channel, 0, &readback);
        if (ret == RET_SUCCESS) {
            printf("[%u/%u] CMD1=0x%04x CDP_STS=0x%08x RT_STS1=0x%08x DATA0=0x%04x DATA31=0x%04x\n",
                   n + 1,
                   repeat,
                   readback.CMD1 & 0xffffu,
                   readback.CDP_STS,
                   readback.Rt_Sts1,
                   readback.Msg_Data[0] & 0xffffu,
                   readback.Msg_Data[31] & 0xffffu);
        } else {
            printf("[%u/%u] BCCDP_Read failed: ret=0x%08x\n", n + 1, repeat, ret);
        }

        if (n + 1 < repeat) {
            Sleep(interval_ms);
        }
    }

    MIL1553_BCStop(handle, channel);
    MIL1553_BC_MODE_Disable(handle, channel);
    MIL1553_DeviceClose(handle);
    return 0;
}
