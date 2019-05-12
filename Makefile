CXX ?= g++
OPTLEVEL ?= 3

CXXFLAGS += -Wall -Wextra -std=gnu++17 -g -flto -O$(OPTLEVEL)

COW_VECTOR ?= 0
ifneq ($(COW_VECTOR),0)
	CXXFLAGS += -DUM_USE_COW_VECTOR
endif

TRACE_OP_CODES ?= 0
ifneq ($(TRACE_OP_CODES),0)
	CXXFLAGS += -DUM_TRACE_OP_CODES=$(TRACE_OP_CODES)
endif

NO_PREDICTION ?= 0
ifneq ($(NO_PREDICTION),0)
	CXXFLAGS += -DUM_NO_PREDICTION=$(NO_PREDICTION)
endif

JEMALLOC ?= 1
ifneq ($(JEMALLOC),0)
	LDFLAGS += -Ljemalloc
endif

ALL_FLAGS := 'CFLAGS=$(CFLAGS) CXXFLAGS=$(CXXFLAGS) LDFLAGS=$(LDFLAGS)'

all: um

# Write our current compiler flags so that we rebuild if they change.
force:
.compiler_flags: force
	@echo '$(ALL_FLAGS)' | cmp -s - $@ || echo '$(ALL_FLAGS)' > $@

um: machine/src/main.cc .compiler_flags
	$(CXX) $(CXXFLAGS) $(LDFLAGS) $< -o $@

.PHONY: bench
bench: um
	@./etc/bench

clean:
	@rm um
