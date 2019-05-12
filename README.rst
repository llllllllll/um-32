UM-32
=====

This is a C++ implementation of the `UM-32 "Universal Machine"
<https://esolangs.org/wiki/UM-32>`_. You can find the specification, various VM
images, and more information about the contest which originally spawned this
horror at boundvariable.org.

I wrote this because a friend did a `Rust implementation
<https://github.com/jgrillo/um32>`_.

Options
-------

When compiling, the following options may be set:

``COW_VECTOR=1``
~~~~~~~~~~~~~~~~

Use copy-on-write vectors for the arrays. This adds a performance penalty to
array reads and writes; but, it make load program much faster in most
cases. This is slightly worse for the midmark and sandmark benchmarks, but the
``uml`` language doesn't currently use self-modifying code, so it makes loading
arrays (calling functions and branches) much faster.

``TRACE_OP_CODES=<path/to/trace``
~~~~~~~~~~~~~~~~~~~~

Write each opcode executed to a binary file defined by the option. This is used
to build the prediction options.

Performance
-----------

.. code-block:: bash

   $ make bench
   g++ (GCC) 8.2.1 20181127
   Copyright (C) 2018 Free Software Foundation, Inc.
   This is free software; see the source for copying conditions.  There is NO
   warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

   Architecture:        x86_64
   CPU op-mode(s):      32-bit, 64-bit
   Byte Order:          Little Endian
   Address sizes:       39 bits physical, 48 bits virtual
   CPU(s):              4
   On-line CPU(s) list: 0-3
   Thread(s) per core:  2
   Core(s) per socket:  2
   Socket(s):           1
   NUMA node(s):        1
   Vendor ID:           GenuineIntel
   CPU family:          6
   Model:               78
   Model name:          Intel(R) Core(TM) i7-6600U CPU @ 2.60GHz
   Stepping:            3
   CPU MHz:             3204.468
   CPU max MHz:         3400.0000
   CPU min MHz:         400.0000
   BogoMIPS:            5618.00
   Virtualization:      VT-x
   L1d cache:           32K
   L1i cache:           32K
   L2 cache:            256K
   L3 cache:            4096K
   NUMA node0 CPU(s):   0-3
   Flags:               fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc art arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf tsc_known_freq pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid sse4_1 sse4_2 x2apic movbe popcnt aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault epb invpcid_single pti tpr_shadow vnmi flexpriority ept vpid ept_ad fsgsbase tsc_adjust bmi1 hle avx2 smep bmi2 erms invpcid rtm mpx rdseed adx smap clflushopt intel_pt xsaveopt xsavec xgetbv1 xsaves dtherm ida arat pln pts hwp hwp_notify hwp_act_window hwp_epp

   analyzing CPU 0:
     driver: intel_pstate
     CPUs which run at the same hardware frequency: 0
     CPUs which need to have their frequency coordinated by software: 0
     maximum transition latency:  Cannot determine or is not supported.
     hardware limits: 400 MHz - 3.40 GHz
     available cpufreq governors: performance powersave
     current policy: frequency should be within 400 MHz and 3.40 GHz.
                     The governor "performance" may decide which speed to use
                     within this range.
     current CPU frequency: Unable to call hardware
     current CPU frequency: 3.20 GHz (asserted by call to kernel)
     boost state support:
       Supported: yes
       Active: yes

   ./um samples/midmark.um
    == UM beginning stress test / benchmark.. ==
   4.   12345678.09abcdef
   3.   6d58165c.2948d58d
   2.   0f63b9ed.1d9c4076
   1.   8dba0fc0.64af8685
   0.   583e02ae.490775c0
   Benchmark complete.

   real	0m0.225s
   user	0m0.221s
   sys	0m0.003s

   ./um samples/sandmark.umz
   trying to Allocate array of size 0..
   trying to Abandon size 0 allocation..
   trying to Allocate size 11..
   trying Array Index on allocated array..
   trying Amendment of allocated array..
   checking Amendment of allocated array..
   trying Alloc(a,a) and amending it..
   comparing multiple allocations..
   pointer arithmetic..
   check old allocation..
   simple tests ok!
   about to load program from some allocated array..
   success.
   verifying that the array and its copy are the same...
   success.
   testing aliasing..
   success.
   free after loadprog..
   success.
   loadprog ok.
    == SANDmark 19106 beginning stress test / benchmark.. ==
   100. 12345678.09abcdef
   99.  6d58165c.2948d58d
   98.  0f63b9ed.1d9c4076

       ...

   3.   7c7394b2.476c1ee5
   2.   f3a52453.19cc755d
   1.   2c80b43d.5646302f
   0.   a8d1619e.5540e6cf
   SANDmark complete.

   real	0m16.275s
   user	0m16.234s
   sys	0m0.006s

``UML`` - The Universal Machine Language
----------------------------------------

What good is a VM without the ability to compile programs for it? The
``compiler`` directory includes a WIP compiler for a simple imperative
programming language that compiles to the UM-32 machine.

The language supports two data types:

1. ``uint``: A scalar platter.
2. ``array``: A fixed-length array of platters. The layout is: ``[length, ix_0,
   ix_1, ..., ix_n]``. String and array are synonyms.


The syntax borrows heavily from Python, for example, a hello world program may
look like:

.. code-block:: python

   def _inner_print(cs: array, n: uint) -> void:
       if n:
           # there are characters left to print
           ix: uint = um.len(cs) - n
           um.putchar(cs[ix])

           # recurse
           _inner_print(cs, n - 1)
       else:
           # no more characters, print the trailing newline
           um.putchar(10)


   def print(cs: array) -> void:
       _inner_print(cs, um.len(cs))


   def main() -> void:
       print("hello world")


``um.putchar`` is a built-in function which writes a single character to the
terminal. ``um.len`` is a built-in function which returns the length of an
array.

See ``compiler/README.rst`` for implementation details.
