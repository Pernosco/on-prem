# on-prem

Tools for running Pernosco on-premises.

## Quick start guide

You will need AWS credentials to download Pernosco container images, i.e. values for environment variables `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. If you don't have these and you want to try out Pernosco on-premises, [contact us](mailto:inquiries@pernos.co).

Make sure the AWS CLI tools are installed and on your `$PATH`. Distribution packages [may fail](https://github.com/aws/aws-cli/issues/2403) so we recommend using
```
sudo pip3 install awscli --upgrade
```

You will need Python 3.8 or later installed. If your default Python is not 3.8 or later, run `python3.8 pernosco ...` below.

Make sure a relatively recent `docker` is installed and on your `$PATH`. Make sure [rr](https://rr-project.org) 5.4.0 or higher is installed and on your path.

Clone this respository and make sure the `pernosco` script is on your `$PATH`.

Add your AWS credentials to the environment and run
```
pernosco pull
```
to pull the Pernosco container images.

Record something with `rr`. Then build a Pernosco database for your recording using
```
pernosco build <trace-dir>
```

Launch the Pernosco client application using
```
pernosco serve --storage <storage-dir> --sources <source-dir> [--tunnel <tunnel parameters>] <trace-dir>
```
where `<source-dir>` is a directory tree containing source files you want to make available in the client. The `--sources` option can be specified multiple times. The `<storage-dir>` should be a directory where Pernosco will store persistent data (e.g. notebook entries) for this trace. If you don't care about keeping state between runs of the client application, you can omit the `--storage` option.

The optional `--tunnel` allows exposing the Pernosco UI outside of the local machine. Values of the form `--tunnel=80` (to expose Pernosco on an arbitrary port on all interfaces and addresses) and `--tunnel=1.2.3.4:80` (to expose Pernosco on the address `1.2.3.4` only) are accepted.

When the client application starts successfully, it will print something like
```
Appserver launched at http://172.29.0.2:3000/index.html
```
Load that link in your Web browser to debug your recording. When done, press ctrl-C in the terminal to kill the client application.

All directories and files created by Pernosco are world-readable/world-writeable, so be careful where you put them.

## Hardware requirements

At minimum the machine running the builder and appserver needs CPU support for AVX (on Intel, Sandy Bridge or later). It needs to support any instructions used in the rr recording.

## Parallelism

Pernosco can be computationally expensive when processing long execution traces. Pernosco has been designed to be highly parallel and is capable of using a very large number of CPU cores. Parallelism during the build phase is controlled by the `--shards` argument to `pernosco build`. The default number of shards is 5, which can saturate an 18 core CPU. If you are running on fewer cores, you may want to try reducing the number of shards, and if you are running on more cores, increasing the number of shards. The smallest number of shards that can saturate your CPU is likely to give the best performance.

## Processing recordings to a shared server

It can be useful to process Pernosco recordings on a shared server instead of locally. You can make an rr recording locally, run `pernosco package-build` on it, copy the trace directory to a server, and there run `pernosco only-build` and `pernosco serve --tunnel`.

## Limiting resource usage

All Pernosco containers are placed in a `pernosco` cgroup. You can place CPU, memory, etc limitations on this cgroup as desired. This may be helpful if you are running Pernosco on an internally shared system and want to keep it from starving other tasks of resources.

## Troubleshooting

Pass `pernosco --log info=<log-file>` to capture a log. Pay attention to lines starting with `ERROR` or `WARN`. Contact [support](mailto:support@pernos.co) for assistance if necessary.

## Updates

When you want to update Pernosco, pull new revisions from this git repository and then rerun `pernosco pull`.

## Confinement

The Pernosco on-premises product comprises the builder and server containers and the `pernosco` script in this repository. The builder and server are closed-source but are confined to run with the minimum access to the outside world needed to do their work. That confinement is performed using `docker` as configured by the `pernosco` script, which is open-source for your inspection (and, if necessary, modification).

The containers require access to the outside world as follows:
* The builder container requires read/write access to the trace directory subtree (due to `docker` limitations, this directory must be writeable by all users). It has no network access at all (but see below).
* The server container requires read access to the trace directory subtree and all specified source directory subtrees (due to `docker` limitations, these directories must be readable by all users). It requires read/write access to the storage directory subtree, if specified (you guessed it, due to `docker` limitations, this directory must be writeable by all users). It has a private network that cannot connect to the outside world, so that you can access its Web server from the local machine.

This confinement largely ensures our containers can't modify or leak data even if they were malicious, but technical limitations mean that confinement is not 100% watertight. Known issues:
* `docker` runs an embedded DNS server accessible to every container which [cannot be disabled](https://github.com/moby/moby/issues/19474). Thus in principle a malicious container could leak information to the outside world via DNS requests. This potential threat could be blocked by blocking DNS on the host.
* Our Web client uses [CSP](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP) to confine itself, preventing it from communicating with any Web servers other than the on-premises Pernosco server itself. However, since our Web client is sending the CSP header, a malicious client could stop doing that. This potential threat could be blocked by putting the Web client behind a proxy that forcibly adds the required CSP header.

### Opting out of seccomp and AppArmor

We disable seccomp syscall filtering and AppArmor in our containers using Docker's `seccomp=unconfined` and `apparmor=unconfined`. The former is necessary because Pernosco uses somewhat exotic syscalls such as `ptrace`, `mount`, `unshare` and `userfaultfd`. The latter is necessary because AppArmor can interfere with operations such as mounting tmpfs in our nested sandboxes. Our containers are still effectively confined by Docker's namespace sandboxing.

### Access to system-debuginfo repositories

Using the `--system-debuginfo` parameter to `pernosco build` and `pernosco package-build` causes packages of relevant system debuginfo to be downloaded from the specified S3 bucket or file system. If you use `s3://pernosco-system-debuginfo-overlays`, that will make requests to our S3 bucket that we could monitor, exposing which Ubuntu packages you might be using with Pernosco. If this is a problem, don't use `--system-debuginfo`, or mirror our bucket to your own bucket or local file server and pass its location to `--system-debuginfo`.

If our bucket is missing some packages or distributions that you want debuginfo for, let us know. Currently we support a subset of library packages, on all Ubuntu releases. Access to `s3://pernosco-system-debuginfo-overlays` requires your on-prem AWS credentials.

## Distro-specific advice

### Debian

Debian comes with user namespace support disabled in the kernel. Pernosco uses user namespaces to sandbox third-party binaries that are used in debugging sessions such as `gdb` and `libthread_db.so` (a glibc component that provides support for accessing TLS variables). You can check the status of user namespace support with `sysctl kernel.unprivileged_userns_clone`: 0 = disabled, 1 = enabled. You will need to enable `kernel.unprivileged_userns_clone` to run Pernosco.

Add `kernel.unprivileged_userns_clone=1` to `/etc/sysctl.conf` to enable it on each subsequent reboot or run `sysctl -w kernel.unprivileged_userns_clone=1` to enable it until the next reboot.

## Open-source licensing commitments

The Pernosco on-prem packages derive from some GPLv3 code:
* *gdb*: We include a gdb binary built from the sources [here](https://github.com/Pernosco/binutils-gdb/tree/pernosco-gdb)

### Software Bill of Materials

The Pernosco on-prem packages contain a Software Bill of Materials (SBOM) that lists included open source software components. The SBOM can be used for compliance and security purposes. Running the command

```
pernosco bom [path]
```

will output the SBOM to the specified directory. If no directory is specified, the current directory is used. A separate file is produced for each container. These files are in the [CycloneDX](https://cyclonedx.org/) format. The third-party [cyclonedx-cli](https://github.com/CycloneDX/cyclonedx-cli) software can be used to diff these components across Pernosco versions to track changes in the constituent components. e.g. `docker run --rm --network none -v $PWD:/local-dir -it cyclonedx/cyclonedx-cli diff --output-format json /local-dir/old/app_server.xml /local-dir/new/app_server.xml`
