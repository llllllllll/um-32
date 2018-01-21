CXX ?= g++

all: um

um: machine/src/main.cc
	$(CXX) -Wall -Wextra -std=gnu++17 -O3 $(CXXFLAGS) $< -o $@

clean:
	@rm um
