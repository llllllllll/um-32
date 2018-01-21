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

``-D UM_COW_VECTOR``
~~~~~~~~~~~~~~~~~~~~

Use copy-on-write vectors for the arrays. This adds a performance penalty to
array reads and writes; but, it make load program much faster in most
cases.

``-D UM_PRINT_OPNAME``
~~~~~~~~~~~~~~~~~~~~~~

Print the name of each instruction during execution. This is useful to provide a
debugging trace when a crash occurs.


Performance
-----------

.. code-block:: bash

   [jo4 um-32]$ sudo lshw -class cpu
     *-cpu
          description: CPU
          product: Intel(R) Core(TM) i7-6600U CPU @ 2.60GHz
          vendor: Intel Corp.
          physical id: 7
          bus info: cpu@0
          version: Intel(R) Core(TM) i7-6600U CPU @ 2.60GHz
          serial: None
          slot: U3E1
          size: 1080MHz
          capacity: 4005MHz
          width: 64 bits
          clock: 100MHz
          capabilities: x86-64 fpu fpu_exception wp vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp constant_tsc art arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf tsc_known_freq pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid sse4_1 sse4_2 x2apic movbe popcnt aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault epb intel_pt tpr_shadow vnmi flexpriority ept vpid fsgsbase tsc_adjust bmi1 hle avx2 smep bmi2 erms invpcid rtm mpx rdseed adx smap clflushopt xsaveopt xsavec xgetbv1 xsaves dtherm ida arat pln pts hwp hwp_notify hwp_act_window hwp_epp cpufreq
       configuration: cores=2 enabledcores=2 threads=4

   [joe um-32]$ time ./um samples/midmark.um
    == UM beginning stress test / benchmark.. ==
   4.   12345678.09abcdef
   3.   6d58165c.2948d58d
   2.   0f63b9ed.1d9c4076
   1.   8dba0fc0.64af8685
   0.   583e02ae.490775c0
   Benchmark complete.

   real	   0m0.405s
   user	   0m0.397s
   sys	   0m0.007s

   [joe um-32]$ time ./um samples/sandmark.umz
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

   real	   0m31.133s
   user	   0m31.084s
   sys	   0m0.007s


``UML`` - The Universal Machine Language
----------------------------------------

What good is a VM without the ability to compile programs for it. the
``compiler`` directory includes a WIP compiler for a simple imperative
programming language that compiles to the UM-32 machine.

The language supports two data types:

1. ``platter``: A scalar platter.
2. ``array``: A fixed-length array of platters. The layout is: ``[length, ix_0,
   ix_1, ..., ix_n]``. String and array are synonyms.


The syntax borrows heavily from Python, for example, a hello world program may
look like:

.. code-block:: python

   def print(cs):
       for c in cs:
           um.putchar(c)

       um.putchar('\n')  # newline

   def main():
       print("Hello World!")


``um.putchar`` is a built-in macro which writes a single character to the
terminal.

See ``compiler/README.rst`` for implementation details.
