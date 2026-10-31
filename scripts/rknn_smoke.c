/* Local hardware-execution smoke test, not an accuracy benchmark. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rknn_api.h"

#define CHECK(expr) do { int status = (expr); if (status < 0) { \
  fprintf(stderr, "FAIL %s: %d\n", #expr, status); goto fail; } } while (0)

int main(int argc, char **argv) {
  if (argc != 2) { fprintf(stderr, "Usage: rknn_smoke MODEL.rknn\n"); return 2; }
  FILE *f = fopen(argv[1], "rb");
  if (!f) { perror("model"); return 1; }
  if (fseek(f, 0, SEEK_END)) { fclose(f); return 1; }
  long size = ftell(f);
  if (size <= 0 || size > 64 * 1024 * 1024) { fclose(f); return 1; }
  rewind(f);
  void *model = malloc((size_t)size);
  if (!model || fread(model, 1, (size_t)size, f) != (size_t)size) { fclose(f); free(model); return 1; }
  fclose(f);
  rknn_context ctx = 0;
  rknn_input *inputs = NULL;
  rknn_output *outputs = NULL;
  uint32_t input_count = 0;
  CHECK(rknn_init(&ctx, model, (uint32_t)size, RKNN_FLAG_COLLECT_PERF_MASK, NULL));
  rknn_sdk_version sdk;
  memset(&sdk, 0, sizeof(sdk));
  CHECK(rknn_query(ctx, RKNN_QUERY_SDK_VERSION, &sdk, sizeof(sdk)));
  printf("RKNN_API=%s RKNN_DRIVER=%s\n", sdk.api_version, sdk.drv_version);
  rknn_input_output_num count;
  CHECK(rknn_query(ctx, RKNN_QUERY_IN_OUT_NUM, &count, sizeof(count)));
  if (!count.n_input || count.n_input > 8 || !count.n_output || count.n_output > 32) goto fail;
  input_count = count.n_input;
  inputs = calloc(count.n_input, sizeof(*inputs));
  outputs = calloc(count.n_output, sizeof(*outputs));
  if (!inputs || !outputs) goto fail;
  for (uint32_t i = 0; i < count.n_input; i++) {
    rknn_tensor_attr attr;
    memset(&attr, 0, sizeof(attr)); attr.index = i;
    CHECK(rknn_query(ctx, RKNN_QUERY_INPUT_ATTR, &attr, sizeof(attr)));
    if (!attr.n_elems || attr.n_elems > 64 * 1024 * 1024) goto fail;
    inputs[i].index = i;
    inputs[i].type = RKNN_TENSOR_UINT8;
    inputs[i].fmt = RKNN_TENSOR_NHWC;
    inputs[i].size = attr.n_elems;
    inputs[i].buf = calloc(attr.n_elems, 1);
    if (!inputs[i].buf) goto fail;
    printf("INPUT_%u elements=%u dimensions=%u\n", i, attr.n_elems, attr.n_dims);
  }
  CHECK(rknn_inputs_set(ctx, count.n_input, inputs));
  for (unsigned run = 0; run < 3; run++) {
    for (uint32_t j = 0; j < count.n_output; j++) {
      memset(&outputs[j], 0, sizeof(outputs[j])); outputs[j].index = j; outputs[j].want_float = 1;
    }
    CHECK(rknn_run(ctx, NULL));
    CHECK(rknn_outputs_get(ctx, count.n_output, outputs, NULL));
    int valid = 1;
    for (uint32_t j = 0; j < count.n_output; j++) {
      if (!outputs[j].buf || !outputs[j].size) { valid = 0; continue; }
      const float *values = outputs[j].buf;
      size_t n = outputs[j].size / sizeof(float);
      if (n > 65536) n = 65536;
      for (size_t k = 0; k < n; k++) if (!isfinite(values[k])) valid = 0;
    }
    rknn_perf_run perf;
    memset(&perf, 0, sizeof(perf));
    int queried = rknn_query(ctx, RKNN_QUERY_PERF_RUN, &perf, sizeof(perf));
    printf("INFERENCE_%u outputs=%u finite=%d hardware_us=%lld perf_status=%d\n",
           run + 1, count.n_output, valid, (long long)perf.run_duration, queried);
    CHECK(rknn_outputs_release(ctx, count.n_output, outputs));
    if (!valid) goto fail;
  }
  printf("NPU_SMOKE_PASS runs=3 input=zeros accuracy_test=false\n");
  for (uint32_t i = 0; i < input_count; i++) free(inputs[i].buf);
  free(inputs); free(outputs); rknn_destroy(ctx); free(model);
  return 0;
fail:
  if (inputs) for (uint32_t i = 0; i < input_count; i++) free(inputs[i].buf);
  free(inputs); free(outputs); if (ctx) rknn_destroy(ctx); free(model);
  return 1;
}
