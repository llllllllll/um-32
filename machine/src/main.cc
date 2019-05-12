#include <array>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <tuple>
#include <vector>

#include "cow_vector.h"

namespace um {
#ifdef UM_USE_COW_VECTOR
template<typename T>
using array_vector = cow_vector<T>;
#else
template<typename T>
using array_vector = std::vector<T>;
#endif

using platter = uint32_t;

enum class opcode : uint8_t {
    conditional_move = 0,
    array_index = 1,
    array_amendment = 2,
    addition = 3,
    multiplication = 4,
    division = 5,
    not_and = 6,
    halt = 7,
    allocation = 8,
    abandonment = 9,
    output = 10,
    input = 11,
    load_program = 12,
    orthography = 13,
};

std::array<std::string, 14> opname = {
    "conditional_move",
    "array_index",
    "array_amendment",
    "addition",
    "multiplication",
    "division",
    "not_and",
    "halt",
    "allocation",
    "abandonment",
    "output",
    "input",
    "load_program",
    "orthography",
};

platter extract_bits(platter p, uint8_t start, uint8_t count) {
    platter mask = ((1 << count) - 1) << start;
    return (p & mask) >> start;
}

struct malformed_program : public std::invalid_argument {
public:
    malformed_program() : std::invalid_argument("malformed_program") {}
};

class machine {
private:
    std::array<platter, 8> m_registers;
    std::vector<platter> m_free_list;
    std::vector<array_vector<platter>> m_arrays;
    std::size_t m_execution_finger;

    opcode read_opcode(platter p) {
        return static_cast<opcode>(extract_bits(p, 28, 4));
    }

    template<std::size_t... ixs>
    auto read_registers(platter p) {
        return std::tie(m_registers[extract_bits(p, 6 - (ixs * 3), 3)]...);
    }

    void conditional_move(platter instruction) {
        auto [a, b, c] = read_registers<0, 1, 2>(instruction);
        if (c) {
            a = b;
        }
    }

    void array_index(platter instruction) {
        auto [a, b, c] = read_registers<0, 1, 2>(instruction);
        a = m_arrays[b][c];
    }

    void array_amendment(platter instruction) {
        auto [a, b, c] = read_registers<0, 1, 2>(instruction);
        m_arrays[a][b] = c;
    }

    void addition(platter instruction) {
        auto [a, b, c] = read_registers<0, 1, 2>(instruction);
        a = b + c;
    }

    void multiplication(platter instruction) {
        auto [a, b, c] = read_registers<0, 1, 2>(instruction);
        a = b * c;
    }

    void division(platter instruction) {
        auto [a, b, c] = read_registers<0, 1, 2>(instruction);
        a = b / c;
    }

    void not_and(platter instruction) {
        auto [a, b, c] = read_registers<0, 1, 2>(instruction);
        a = ~(b & c);
    }

    void halt(platter) {
        std::exit(0);
    }

    void allocation(platter instruction) {
        auto [b, c] = read_registers<1, 2>(instruction);
        if (m_free_list.size()) {
            platter address = m_free_list.back();
            m_free_list.pop_back();

            auto& vec = m_arrays[address];
            vec.insert(vec.begin(), c, 0);

            b = address;
        }
        else {
            m_arrays.emplace_back(c, 0);
            b = m_arrays.size() - 1;
        }
    }

    void abandonment(platter instruction) {
        auto [c] = read_registers<2>(instruction);
        m_arrays[c].clear();
        m_free_list.push_back(c);
    }

    void output(platter instruction) {
        auto [c] = read_registers<2>(instruction);
        std::putchar(c);
    }

    void input(platter instruction) {
        auto [c] = read_registers<2>(instruction);
        c = std::getchar();
    }

    void load_program(platter instruction) {
        auto [b, c] = read_registers<1, 2>(instruction);
        m_execution_finger = c;
        if (b) {
            m_arrays[0] = m_arrays[b];
        }
    }

    void orthography(platter instruction) {
        std::uint8_t a_index = extract_bits(instruction, 25, 3);
        platter value = extract_bits(instruction, 0, 25);

        m_registers[a_index] = value;
    }

public:
    machine(array_vector<platter>&& program)
        : m_registers({0, 0, 0, 0, 0, 0, 0, 0}),
          m_arrays({std::move(program)}),
          m_execution_finger(0) {}

    static machine parse(std::istream& stream) {
        stream.seekg(0, stream.end);
        std::size_t size = stream.tellg();
        stream.seekg(0);

        if (size % 4) {
            throw malformed_program();
        }

        array_vector<platter> program(size / 4);

        stream.read(reinterpret_cast<char*>(program.data()), size);

        for (platter& p : program) {
            p = __builtin_bswap32(p);
        }
        return machine(std::move(program));
    }

    void step() {
        platter instruction = m_arrays[0][m_execution_finger++];
        switch (read_opcode(instruction)) {
        case opcode::conditional_move:
            conditional_move(instruction);
            return;
        case opcode::array_index:
            array_index(instruction);
            return;
        case opcode::array_amendment:
            array_amendment(instruction);
            return;
        case opcode::addition:
            addition(instruction);
            return;
        case opcode::multiplication:
            multiplication(instruction);
            return;
        case opcode::division:
            division(instruction);
            return;
        case opcode::not_and:
            not_and(instruction);
            return;
        case opcode::halt:
            halt(instruction);
            return;
        case opcode::allocation:
            allocation(instruction);
            return;
        case opcode::abandonment:
            abandonment(instruction);
            return;
        case opcode::output:
            output(instruction);
            return;
        case opcode::input:
            input(instruction);
            return;
        case opcode::load_program:
            load_program(instruction);
            return;
        case opcode::orthography:
            orthography(instruction);
            return;
        }
    }

    void run() {
        while (true) {
            step();
        }
    }
};
}  // namespace um

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: " << argv[0] << " PROGRAM\n";
        return -1;
    }

    std::fstream stream(argv[1], stream.binary | stream.in);

    try {
        um::machine::parse(stream).run();
    }
    catch (const um::malformed_program& e) {
        std::cerr << e.what() << '\n';
        return -1;
    }
    return 0;
}
