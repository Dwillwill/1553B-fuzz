#ifndef MIL1553_BOARD_ADAPTER_H
#define MIL1553_BOARD_ADAPTER_H

#include <stdint.h>

#ifdef _WIN32
#define MIL1553_ADAPTER_CALL __stdcall
#ifdef MIL1553_ADAPTER_STATIC
#define MIL1553_ADAPTER_API
#elif defined(MIL1553_ADAPTER_BUILD_DLL)
#define MIL1553_ADAPTER_API __declspec(dllexport)
#else
#define MIL1553_ADAPTER_API __declspec(dllimport)
#endif
#else
#define MIL1553_ADAPTER_CALL
#define MIL1553_ADAPTER_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

enum {
    MIL1553_ADAPTER_OK = 0,
    MIL1553_ADAPTER_ERR_BAD_ARG = 0x10001,
    MIL1553_ADAPTER_ERR_NOT_OPEN = 0x10002,
    MIL1553_ADAPTER_ERR_CANCELLED = 0x10003,
    MIL1553_ADAPTER_ERR_API_BASE = 0x20000
};

typedef struct Mil1553Adapter Mil1553Adapter;

typedef struct Mil1553FuzzCase {
    uint8_t rt_addr;
    uint8_t tx_rx;
    uint8_t subaddr;
    uint8_t word_count;
    uint8_t is_rt_to_rt;
    uint8_t rt2_addr;
    uint8_t rt2_tx_rx;
    uint8_t rt2_subaddr;
    uint8_t rt2_word_count;
    uint32_t bcmsg_fmt;
    uint32_t bcmsg_rty;
    uint32_t delay_100ns;
    uint32_t sched_time_100ns;
    uint32_t frame_time_100ns;
    uint32_t next_msg_num;
    uint32_t data_words[32];
} Mil1553FuzzCase;

typedef struct Mil1553Readback {
    uint32_t cdp_sts;
    uint32_t time_tag_h;
    uint32_t time_tag_l;
    uint32_t cmd1;
    uint32_t cmd2;
    uint32_t rt_sts1;
    uint32_t rt_sts2;
    uint32_t msg_data[32];
} Mil1553Readback;

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_create(Mil1553Adapter **out_adapter);
MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_destroy(Mil1553Adapter *adapter);

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_open(
    Mil1553Adapter *adapter,
    uint8_t card_index,
    uint8_t channel);

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_close(Mil1553Adapter *adapter);
MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_reset(Mil1553Adapter *adapter);

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_prepare(
    Mil1553Adapter *adapter,
    uint32_t max_msg_count,
    uint16_t subframe_count);

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_load_cases(
    Mil1553Adapter *adapter,
    const Mil1553FuzzCase *cases,
    uint32_t case_count);

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_start(
    Mil1553Adapter *adapter,
    uint32_t start_msg_num);

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_wait_done(
    Mil1553Adapter *adapter,
    uint32_t timeout_ms);

/* Thread-safe: records a cancellation request without calling the vendor API. */
MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_request_stop(
    Mil1553Adapter *adapter);

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_stop(Mil1553Adapter *adapter);

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_bc_readback(
    Mil1553Adapter *adapter,
    uint16_t msg_num,
    Mil1553Readback *out_readback);

MIL1553_ADAPTER_API uint32_t MIL1553_ADAPTER_CALL mil1553_adapter_last_vendor_status(
    Mil1553Adapter *adapter);

#ifdef __cplusplus
}
#endif

#endif
