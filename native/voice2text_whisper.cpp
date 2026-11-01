// Small C interface over whisper.cpp, called from gpu_engine.py through ctypes.
// whisper_full_params changes between releases, so Python never touches it.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "ggml-backend.h"
#include "whisper.h"

#define V2T_API extern "C" __declspec(dllexport)

static void silent_log(ggml_log_level, const char *, void *) {}

static size_t read_file(void * file, void * output, size_t size) {
    return fread(output, 1, size, static_cast<FILE *>(file));
}

static bool at_end(void * file) {
    return feof(static_cast<FILE *>(file)) != 0;
}

static void close_file(void * file) {
    fclose(static_cast<FILE *>(file));
}

// Writes the first GPU's name; returns 0 when Vulkan offers no GPU.
V2T_API int v2t_gpu_name(char * output, int size) {
    try {
        whisper_log_set(silent_log, nullptr);
        for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
            ggml_backend_dev_t device = ggml_backend_dev_get(i);
            enum ggml_backend_dev_type type = ggml_backend_dev_type(device);
            if (type == GGML_BACKEND_DEVICE_TYPE_GPU || type == GGML_BACKEND_DEVICE_TYPE_IGPU) {
                snprintf(output, size, "%s", ggml_backend_dev_description(device));
                return 1;
            }
        }
    } catch (...) {
    }
    return 0;
}

// Takes a wide path: fopen would fail on folders outside the system code page.
V2T_API whisper_context * v2t_load(const wchar_t * path) {
    try {
        FILE * file = _wfopen(path, L"rb");
        if (file == nullptr) {
            return nullptr;
        }
        whisper_model_loader loader = {file, read_file, at_end, close_file};
        whisper_context_params params = whisper_context_default_params();
        params.use_gpu = true;
        return whisper_init_with_params(&loader, params);
    } catch (...) {
        return nullptr;
    }
}

V2T_API void v2t_unload(whisper_context * context) {
    whisper_free(context);
}

// Returns UTF-8 text to release with v2t_free_text, or null on failure.
V2T_API char * v2t_transcribe(whisper_context * context, const float * samples, int count,
                              const char * language, int threads) {
    try {
        whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_BEAM_SEARCH);
        params.n_threads = threads;
        params.n_max_text_ctx = 0;
        params.no_context = true;
        params.print_progress = false;
        params.print_realtime = false;
        params.print_special = false;
        params.print_timestamps = false;
        params.language = language;
        params.greedy.best_of = 5;
        params.beam_search.beam_size = 5;
        if (whisper_full(context, params, samples, count) != 0) {
            return nullptr;
        }
        std::string text;
        for (int i = 0; i < whisper_full_n_segments(context); ++i) {
            text += whisper_full_get_segment_text(context, i);
        }
        return _strdup(text.c_str());
    } catch (...) {
        return nullptr;
    }
}

V2T_API void v2t_free_text(char * text) {
    free(text);
}
