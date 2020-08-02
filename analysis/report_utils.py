# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Utility functions for coverage report generation."""

import os
import multiprocessing

from common import filesystem
from common import experiment_utils
from common import new_process
from common import benchmark_utils
from common import logs
from experiment.build import build_utils
from experiment import measurer

logger = logs.Logger('reporter')  # pylint: disable=invalid-name


def get_profdata_file_path(fuzzer, benchmark, trial_id):
    """Get profdata file path for a specific trial."""
    benchmark_fuzzer_trial_dir = experiment_utils.get_trial_dir(
        fuzzer, benchmark, trial_id)
    work_dir = experiment_utils.get_work_dir()
    measurement_dir = os.path.join(work_dir, 'measurement-folders',
                                   benchmark_fuzzer_trial_dir)
    return os.path.join(measurement_dir, 'reports', 'data.profdata')


def merge_profdata_files(src_files, dst_file):
    """Merge profdata files from |src_files| to |dst_files|."""
    command = ['llvm-profdata', 'merge', '-sparse'
              ] + src_files + ['-o', dst_file]
    result = new_process.execute(command, expect_zero=False)
    if result.retcode != 0:
        logger.error('Profdata files merging failed.')


def fetch_source_files(benchmarks, report_dir):
    """Fetch source files to |report_dir|."""
    for benchmark in benchmarks:
        coverage_binaries_dir = build_utils.get_coverage_binaries_dir()
        src_path = os.path.join(coverage_binaries_dir, benchmark, 'src-files')
        dst_dir = os.path.join(report_dir, benchmark, 'src-files')
        filesystem.copytree(src_path, dst_dir)


def get_profdata_files(experiment, benchmarks, fuzzers, report_dir):
    """Get profdata files to |report_dir|."""
    for benchmark in benchmarks:
        for fuzzer in fuzzers:
            trial_ids = measurer.get_trial_ids(experiment, fuzzer, benchmark)
            logger.info('trial ids for profdata is:{trial}'.format(trial=str(trial_ids)))
            files_to_merge = [
                get_profdata_file_path(fuzzer, benchmark, trial_id)
                for trial_id in trial_ids
            ]
            logger.info('files to merge is :{files}'.format(files=str(files_to_merge)))
            dst_dir = os.path.join(report_dir, benchmark, fuzzer)
            filesystem.create_directory(dst_dir)
            dst_file = os.path.join(dst_dir, 'merged.profdata')
            merge_profdata_files(files_to_merge, dst_file)


def fetch_binary_files(benchmarks, report_dir):
    """Get binary file for each benchmark."""
    for benchmark in benchmarks:
        src_file = measurer.get_coverage_binary(benchmark)
        dst_dir = os.path.join(report_dir, benchmark)
        filesystem.copy(src_file, dst_dir)


def generate_cov_reports(benchmarks, fuzzers, report_dir):
    """Generate coverage reports for each benchmark and fuzzer."""
    logger.info('Start generating coverage report for benchmarks.')
    with multiprocessing.Pool() as pool:
        generate_cov_report_args = [(benchmark, fuzzer, report_dir)
                                    for benchmark in benchmarks
                                    for fuzzer in fuzzers]
        result = pool.starmap_async(generate_cov_report, generate_cov_report_args)
        while not result.ready():
            pass
    logger.info('Finished generating coverage report.')


def generate_cov_report(benchmark, fuzzer, report_dir):
    """Generate the coverage report for one pair of benchmark and fuzzer."""
    logger.info('Generating coverage report for benchmark:{benchmark} \
                fuzzer:{fuzzer}'.format(benchmark=benchmark, fuzzer=fuzzer))
    dst_dir = os.path.join(report_dir, benchmark, fuzzer)
    fuzz_target = benchmark_utils.get_fuzz_target(benchmark)
    profdata_file_path = os.path.join(dst_dir, 'merged.profdata')
    binary_file_path = os.path.join(report_dir, benchmark, fuzz_target)
    source_file_path_prefix = os.path.join(report_dir, benchmark, 'src-files')
    command = ['llvm-cov', 'show', '-format=html',
               '-path-equivalence=/,{prefix}'.format(
                   prefix=source_file_path_prefix),
               '-output-dir={dst_dir}'.format(dst_dir=dst_dir),
               '-Xdemangler', 'c++filt', '-Xdemangler', '-n', binary_file_path,
               '-instr-profile={profdata}'.format(profdata=profdata_file_path)]
    result = new_process.execute(command, expect_zero=False)
    if result.retcode != 0:
        logger.error(
            'Coverage report generation failed for fuzzer:{fuzzer},\
             benchmark:{benchmark}.'.format(fuzzer=fuzzer, benchmark=benchmark)
            )