#include "mil1553_board_adapter.h"

#include <atomic>
#include <stddef.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif

#include "mil1553api.h"
#include "mil1553defs.h"
#include "mil1553types.h"

struct Mil1553Adapter {
    ZHANDLE handle;
    uint8_t channel;
    uint32_t last_vendor_status;
    int is_open;
    int bc_mode_enabled;
    int bc_prepared;
    int bc_running;
    std::atomic<int> stop_requested;
};

static uint32_t map_vendor_status(Mil1553Adapter *adapter, uint32_t status)
{
    if (adapter != NULL) {
        adapter->last_vendor_status = status;
    }
    if (status == RET_SUCCESS) {
        return MIL1553_ADAPTER_OK;
    }
    return MIL1553_ADAPTER_ERR_API_BASE | (status & 0xffffu);
}

static void sleep_ms(uint32_t ms)
{
#ifdef _WIN32
    Sleep(ms);
#else
    struct timespec ts;
    ts.tv_sec = ms / 1000u;
    ts.tv_nsec = (long)(ms % 1000u) * 1000000L;
    nanosleep(&ts, NULL);
#endif
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_create(Mil1553Adapter **out_adapter)
{
    if (out_adapter == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }

    Mil1553Adapter *adapter = new Mil1553Adapter;
    adapter->handle = -1;
    adapter->channel = 0;
    adapter->last_vendor_status = RET_SUCCESS;
    adapter->is_open = 0;
    adapter->bc_mode_enabled = 0;
    adapter->bc_prepared = 0;
    adapter->bc_running = 0;
    adapter->stop_requested.store(0);
    *out_adapter = adapter;
    return MIL1553_ADAPTER_OK;
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_destroy(Mil1553Adapter *adapter)
{
    if (adapter == NULL) {
        return MIL1553_ADAPTER_OK;
    }
    mil1553_adapter_close(adapter);
    delete adapter;
    return MIL1553_ADAPTER_OK;
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_open(
    Mil1553Adapter *adapter,
    uint8_t card_index,
    uint8_t channel)
{
    if (adapter == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    if (adapter->is_open) {
        mil1553_adapter_close(adapter);
    }

    uint32_t ret = MIL1553_DeviceOpen(&adapter->handle, card_index);
    if (ret != RET_SUCCESS) {
        adapter->is_open = 0;
        return map_vendor_status(adapter, ret);
    }

    adapter->channel = channel;
    adapter->is_open = 1;
    adapter->bc_mode_enabled = 0;
    adapter->bc_prepared = 0;
    adapter->bc_running = 0;
    adapter->stop_requested.store(0);
    adapter->last_vendor_status = RET_SUCCESS;
    return MIL1553_ADAPTER_OK;
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_close(Mil1553Adapter *adapter)
{
    if (adapter == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    if (!adapter->is_open) {
        return MIL1553_ADAPTER_OK;
    }

    if (adapter->bc_running) {
        MIL1553_BCStop(adapter->handle, adapter->channel);
    }
    if (adapter->bc_mode_enabled) {
        MIL1553_BC_MODE_Disable(adapter->handle, adapter->channel);
    }
    uint32_t ret = MIL1553_DeviceClose(adapter->handle);
    adapter->handle = -1;
    adapter->is_open = 0;
    adapter->bc_mode_enabled = 0;
    adapter->bc_prepared = 0;
    adapter->bc_running = 0;
    adapter->stop_requested.store(0);
    return map_vendor_status(adapter, ret);
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_reset(Mil1553Adapter *adapter)
{
    if (adapter == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    if (!adapter->is_open) {
        return MIL1553_ADAPTER_ERR_NOT_OPEN;
    }

    uint32_t ret = MIL1553_DeviceReset(adapter->handle, adapter->channel);
    if (ret == RET_SUCCESS) {
        adapter->bc_mode_enabled = 0;
        adapter->bc_prepared = 0;
        adapter->bc_running = 0;
    }
    return map_vendor_status(adapter, ret);
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_prepare(
    Mil1553Adapter *adapter,
    uint32_t max_msg_count,
    uint16_t subframe_count)
{
    if (adapter == NULL || max_msg_count == 0) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    if (!adapter->is_open) {
        return MIL1553_ADAPTER_ERR_NOT_OPEN;
    }

    uint32_t ret = MIL1553_BC_MODE_Enable(adapter->handle, adapter->channel);
    if (ret != RET_SUCCESS) {
        return map_vendor_status(adapter, ret);
    }
    adapter->bc_mode_enabled = 1;

    ret = MIL1553_BCInit(adapter->handle, adapter->channel, max_msg_count, subframe_count);
    if (ret != RET_SUCCESS) {
        return map_vendor_status(adapter, ret);
    }

    adapter->bc_prepared = 1;
    adapter->last_vendor_status = RET_SUCCESS;
    return MIL1553_ADAPTER_OK;
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_load_cases(
    Mil1553Adapter *adapter,
    const Mil1553FuzzCase *cases,
    uint32_t case_count)
{
    if (adapter == NULL || cases == NULL || case_count == 0) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    if (!adapter->is_open || !adapter->bc_prepared) {
        return MIL1553_ADAPTER_ERR_NOT_OPEN;
    }

    for (uint32_t i = 0; i < case_count; ++i) {
        const Mil1553FuzzCase *test_case = &cases[i];

        MIL_1553BCCB_STRUCT bccb;
        memset(&bccb, 0, sizeof(bccb));
        bccb.BCMSG_FMT = test_case->bcmsg_fmt;
        if (test_case->is_rt_to_rt) {
            bccb.BCMSG_FMT |= RT2RT;
        }
        bccb.BCMSG_DELAY_TIME = test_case->delay_100ns;
        bccb.BCMSG_SCHE_TIME = test_case->sched_time_100ns;
        bccb.BCFRAME_TIME = test_case->frame_time_100ns;
        bccb.BCMSG_RTY = test_case->bcmsg_rty;

        uint32_t ret = MIL1553_BCCB_Write(adapter->handle, adapter->channel, (ZUINT16)i, &bccb);
        if (ret != RET_SUCCESS) {
            return map_vendor_status(adapter, ret);
        }

        MIL_1553CDP_STRUCT cdp;
        memset(&cdp, 0, sizeof(cdp));
        ret = MIL1553_GetCmdWord(
            test_case->rt_addr,
            test_case->tx_rx,
            test_case->subaddr,
            test_case->word_count,
            &cdp.CMD1);
        if (ret != RET_SUCCESS) {
            return map_vendor_status(adapter, ret);
        }

        if (test_case->is_rt_to_rt) {
            ret = MIL1553_GetCmdWord(
                test_case->rt2_addr,
                test_case->rt2_tx_rx,
                test_case->rt2_subaddr,
                test_case->rt2_word_count,
                &cdp.CMD2);
            if (ret != RET_SUCCESS) {
                return map_vendor_status(adapter, ret);
            }
        }

        cdp.CUR_MSG_NUM = i;
        cdp.NEXT_MSG_NUM = test_case->next_msg_num;
        if (i + 1u < case_count && cdp.NEXT_MSG_NUM == 0u) {
            cdp.NEXT_MSG_NUM = i + 1u;
        } else if (i + 1u == case_count && cdp.NEXT_MSG_NUM == 0u) {
            cdp.NEXT_MSG_NUM = NO_NEXT;
        }
        memcpy(cdp.Msg_Data, test_case->data_words, sizeof(cdp.Msg_Data));

        ret = MIL1553_BCCDP_Write(adapter->handle, adapter->channel, (ZUINT16)i, &cdp);
        if (ret != RET_SUCCESS) {
            return map_vendor_status(adapter, ret);
        }
    }

    adapter->last_vendor_status = RET_SUCCESS;
    return MIL1553_ADAPTER_OK;
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_start(
    Mil1553Adapter *adapter,
    uint32_t start_msg_num)
{
    if (adapter == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    if (!adapter->is_open || !adapter->bc_prepared) {
        return MIL1553_ADAPTER_ERR_NOT_OPEN;
    }

    uint32_t ret = MIL1553_BCStart(adapter->handle, adapter->channel, start_msg_num);
    if (ret == RET_SUCCESS) {
        adapter->bc_running = 1;
    }
    return map_vendor_status(adapter, ret);
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_wait_done(
    Mil1553Adapter *adapter,
    uint32_t timeout_ms)
{
    if (adapter == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    if (!adapter->is_open) {
        return MIL1553_ADAPTER_ERR_NOT_OPEN;
    }

    uint32_t waited = 0;
    for (;;) {
        if (adapter->stop_requested.load() != 0) {
            uint32_t stop_ret = MIL1553_BCStop(adapter->handle, adapter->channel);
            if (stop_ret != RET_SUCCESS) {
                return map_vendor_status(adapter, stop_ret);
            }
            adapter->bc_running = 0;
            adapter->last_vendor_status = RET_SUCCESS;
            return MIL1553_ADAPTER_ERR_CANCELLED;
        }

        uint32_t is_running = 0;
        uint32_t ret = MIL1553_BCIsRunning(adapter->handle, adapter->channel, &is_running);
        if (ret != RET_SUCCESS) {
            return map_vendor_status(adapter, ret);
        }
        if (is_running == 0) {
            adapter->bc_running = 0;
            adapter->last_vendor_status = RET_SUCCESS;
            return MIL1553_ADAPTER_OK;
        }
        if (timeout_ms != 0 && waited >= timeout_ms) {
            MIL1553_BCStop(adapter->handle, adapter->channel);
            adapter->bc_running = 0;
            return MIL1553_ADAPTER_ERR_API_BASE | 0xffffu;
        }
        sleep_ms(1);
        ++waited;
    }
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_request_stop(Mil1553Adapter *adapter)
{
    if (adapter == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    adapter->stop_requested.store(1);
    return MIL1553_ADAPTER_OK;
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_stop(Mil1553Adapter *adapter)
{
    if (adapter == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    if (!adapter->is_open) {
        return MIL1553_ADAPTER_ERR_NOT_OPEN;
    }
    uint32_t ret = MIL1553_BCStop(adapter->handle, adapter->channel);
    if (ret == RET_SUCCESS) {
        adapter->bc_running = 0;
    }
    return map_vendor_status(adapter, ret);
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_readback(
    Mil1553Adapter *adapter,
    uint16_t msg_num,
    Mil1553Readback *out_readback)
{
    if (adapter == NULL || out_readback == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    if (!adapter->is_open) {
        return MIL1553_ADAPTER_ERR_NOT_OPEN;
    }

    MIL_1553CDP_STRUCT cdp;
    memset(&cdp, 0, sizeof(cdp));
    uint32_t ret = MIL1553_BCCDP_Read(adapter->handle, adapter->channel, msg_num, &cdp);
    if (ret != RET_SUCCESS) {
        return map_vendor_status(adapter, ret);
    }

    memset(out_readback, 0, sizeof(*out_readback));
    out_readback->cdp_sts = cdp.CDP_STS;
    out_readback->time_tag_h = cdp.TIME_Tag_H;
    out_readback->time_tag_l = cdp.TIME_Tag_L;
    out_readback->cmd1 = cdp.CMD1;
    out_readback->cmd2 = cdp.CMD2;
    out_readback->rt_sts1 = cdp.Rt_Sts1;
    out_readback->rt_sts2 = cdp.Rt_Sts2;
    memcpy(out_readback->msg_data, cdp.Msg_Data, sizeof(out_readback->msg_data));
    adapter->last_vendor_status = RET_SUCCESS;
    return MIL1553_ADAPTER_OK;
}

uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_last_vendor_status(Mil1553Adapter *adapter)
{
    if (adapter == NULL) {
        return MIL1553_ADAPTER_ERR_BAD_ARG;
    }
    return adapter->last_vendor_status;
}
