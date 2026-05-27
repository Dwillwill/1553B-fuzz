#include "mil1553_board_adapter.h"

#include <stdlib.h>
#include <stdio.h>
#include <string.h>

static int check(const char *step, uint32_t status, Mil1553Adapter *adapter)
{
    if (status == MIL1553_ADAPTER_OK) {
        return 0;
    }
    printf("%s failed: adapter_status=0x%08x vendor_status=0x%08x\n",
           step,
           status,
           adapter != NULL ? mil1553_adapter_last_vendor_status(adapter) : 0);
    return 1;
}

int main(int argc, char **argv)
{
    uint8_t card_index = 0;
    uint8_t channel = 0;
    if (argc > 1) {
        card_index = (uint8_t)atoi(argv[1]);
    }
    if (argc > 2) {
        channel = (uint8_t)atoi(argv[2]);
    }

    Mil1553Adapter *adapter = NULL;
    if (check("create", mil1553_adapter_create(&adapter), adapter)) {
        return 1;
    }
    if (check("open", mil1553_adapter_open(adapter, card_index, channel), adapter)) {
        mil1553_adapter_destroy(adapter);
        return 1;
    }
    if (check("reset", mil1553_adapter_reset(adapter), adapter)) {
        mil1553_adapter_destroy(adapter);
        return 1;
    }
    if (check("bc_prepare", mil1553_adapter_bc_prepare(adapter, 16, 0), adapter)) {
        mil1553_adapter_destroy(adapter);
        return 1;
    }

    Mil1553FuzzCase test_case;
    memset(&test_case, 0, sizeof(test_case));
    test_case.rt_addr = 1;
    test_case.tx_rx = 0;
    test_case.subaddr = 1;
    test_case.word_count = 0;
    test_case.delay_100ns = 1000;
    for (uint32_t i = 0; i < 32; ++i) {
        test_case.data_words[i] = 0x1000u + i;
    }

    if (check("bc_load_cases", mil1553_adapter_bc_load_cases(adapter, &test_case, 1), adapter)) {
        mil1553_adapter_destroy(adapter);
        return 1;
    }
    if (check("bc_start", mil1553_adapter_bc_start(adapter, 0), adapter)) {
        mil1553_adapter_destroy(adapter);
        return 1;
    }
    if (check("bc_wait_done", mil1553_adapter_bc_wait_done(adapter, 3000), adapter)) {
        mil1553_adapter_destroy(adapter);
        return 1;
    }

    Mil1553Readback readback;
    if (check("bc_readback", mil1553_adapter_bc_readback(adapter, 0, &readback), adapter)) {
        mil1553_adapter_destroy(adapter);
        return 1;
    }

    printf("cmd1=0x%04x cdp_sts=0x%08x rt_sts1=0x%08x data0=0x%04x\n",
           readback.cmd1 & 0xffffu,
           readback.cdp_sts,
           readback.rt_sts1,
           readback.msg_data[0] & 0xffffu);

    mil1553_adapter_destroy(adapter);
    return 0;
}
