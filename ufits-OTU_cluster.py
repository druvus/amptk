#!/usr/bin/env python

#This script runs USEARCH OTU clustering
#written by Jon Palmer palmer.jona at gmail dot com

import sys, os, argparse, subprocess, inspect, csv, re, logging
from Bio import SeqIO

#get script path for directory
script_path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

class MyFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def __init__(self,prog):
        super(MyFormatter,self).__init__(prog,max_help_position=50)
class col:
    GRN = '\033[92m'
    END = '\033[0m'
    WARN = '\033[93m'

parser=argparse.ArgumentParser(prog='ufits-OTU_cluster.py', usage="%(prog)s [options] -i file.demux.fq\n%(prog)s -h for help menu",
    description='''Script runs UPARSE OTU clustering. 
    Requires USEARCH by Robert C. Edgar: http://drive5.com/usearch''',
    epilog="""Written by Jon Palmer (2015)  palmer.jona@gmail.com""",
    formatter_class=MyFormatter)

parser.add_argument('-i','--fastq', dest="FASTQ", required=True, help='FASTQ file (Required)')
parser.add_argument('-o','--out', default='out', help='Base output name')
parser.add_argument('-e','--maxee', default='1.0', help='Quality trim EE value')
parser.add_argument('-p','--pct_otu', default='97', help="OTU Clustering Percent")
parser.add_argument('-m','--minsize', default='2', help='Min size to keep for clustering')
parser.add_argument('-l','--length', default='250', help='Length to trim reads')
parser.add_argument('-u','--usearch', dest="usearch", default='usearch8', help='USEARCH8 EXE')
parser.add_argument('--mock', default="False", help='Spike-in control: <barcode label>')
parser.add_argument('--mc', default='ufits_mock3.fa', help='Multi-Fasta Mock Community')
parser.add_argument('--uchime_ref', default='False', choices=['ITS1','ITS2','Full'], help='Run UCHIME REF')
parser.add_argument('--map_unfiltered', action='store_true', help='map original reads back to OTUs')
parser.add_argument('--unoise', action='store_true', help='Run De-noising (UNOISE)')
parser.add_argument('--size_annotations', action='store_true', help='Append size annotations')
args=parser.parse_args()

def countfasta(input):
    count = 0
    with open(input, 'r') as f:
        for line in f:
            if line.startswith (">"):
                count += 1
    return count

def countfastq(input):
    lines = sum(1 for line in open(input))
    count = int(lines) / 4
    return count

def convertSize(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix) 

def checkfastqsize(input):
    filesize = os.path.getsize(input)
    return filesize

def dereplicate(input, output):
    seqs = {}
    in_file = open(input, 'r')
    for rec in SeqIO.parse(in_file, 'fastq'):
        sequence = str(rec.seq)
        if sequence not in seqs:
            seqs[sequence]=rec.id+'size=1;'
        else:
            count = int(seqs[sequence].split('=')[-1].rstrip(';')) + 1
            formated_string = seqs[sequence].rsplit('=', 1)[0]+'='+str(count)+';'
            seqs[sequence] = formated_string
    with open(output, 'wb') as out:
        for sequence in seqs:
            out.write('>'+seqs[sequence]+'\n'+sequence+'\n')

def setupLogging(LOGNAME):
    global log
    stdoutformat = logging.Formatter(col.GRN+'%(asctime)s'+col.END+': %(message)s', datefmt='%b-%d-%Y %I:%M:%S %p')
    fileformat = logging.Formatter('%(asctime)s: %(message)s')
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    sth = logging.StreamHandler()
    sth.setLevel(logging.INFO)
    sth.setFormatter(stdoutformat)
    log.addHandler(sth)
    fhnd = logging.FileHandler(LOGNAME)
    fhnd.setLevel(logging.DEBUG)
    fhnd.setFormatter(fileformat)
    log.addHandler(fhnd)

#remove logfile if exists
log_name = args.out + '.log'
if os.path.isfile(log_name):
    os.remove(log_name)

setupLogging(log_name)
FNULL = open(os.devnull, 'w')
cmd_args = " ".join(sys.argv)+'\n'
log.debug(cmd_args)
print "-------------------------------------------------------"

#initialize script, log system info and usearch version
log.info("Operating system: %s" % sys.platform)
usearch = args.usearch
try:
    usearch_test = subprocess.Popen([usearch, '-version'], stdout=subprocess.PIPE).communicate()[0]
except OSError:
    log.warning("%s not found in your PATH, exiting." % usearch)
    os._exit(1)
log.info("USEARCH version: %s" % usearch_test)

#Count FASTQ records
log.info("Loading FASTQ Records")
total = countfastq(args.FASTQ)
log.info('{0:,}'.format(total) + ' reads')
size = checkfastqsize(args.FASTQ)
readablesize = convertSize(size)
if size >= 4294967296:
    print col.WARN + "Warning, file is larger than 4 GB, you will need USEARCH 64 bit to cluster OTUs, exiting now." + col.END
    os._exit(1)

#usearch8 fastq filtering step - expected errors
filter_out = args.out + '.EE' + args.maxee + '.filter.fq'
log.info("Quality Filtering, expected errors < %s (USEARCH8)" % args.maxee)
log.debug("%s -fastq_filter %s -fastq_trunclen %s -fastq_maxee %s -fastqout %s" % (usearch, args.FASTQ, args.length, args.maxee, filter_out))
subprocess.call([usearch, '-fastq_filter', args.FASTQ, '-fastq_trunclen', args.length, '-fastq_maxee', args.maxee, '-fastqout', filter_out], stdout = FNULL, stderr = FNULL)
total = countfastq(filter_out)
log.info('{0:,}'.format(total) + ' reads passed')

#now run full length dereplication (biopython)
derep_out = args.out + '.EE' + args.maxee + '.derep.fa'
log.info("De-replication (remove duplicate reads)")
dereplicate(filter_out, derep_out)
total = countfasta(derep_out)
log.info('{0:,}'.format(total) + ' reads passed')

#optional run UNOISE
if args.unoise:
    unoise_out = args.out + '.EE' + args.maxee + '.denoised.fa'
    log.info("Denoising Data with UNOISE")
    log.debug("%s -cluster_fast %s -centroids %s -id 0.9 -maxdiffs 5 -abskew 10 -sizein -sizeout -sort size" % (usearch, derep_out, unoise_out))
    subprocess.call([usearch, '-cluster_fast', derep_out, '-centroids', unoise_out, '-id', '0.9', '-maxdiffs', '5', '-abskew', '10', '-sizein', '-sizeout', '-sort', 'size'], stdout = FNULL, stderr = FNULL)
    total = countfasta(unoise_out)
    log.info('{0:,}'.format(total) + ' reads passed')
else:
    unoise_out = derep_out

#now run usearch 8 sort by size
sort_out = args.out + '.EE' + args.maxee + '.sort.fa'
log.info("Sorting reads by size (USEARCH8)")
log.debug("%s -sortbysize %s -minsize %s -fastaout %s" % (usearch, unoise_out, args.minsize, sort_out))
subprocess.call([usearch, '-sortbysize', unoise_out, '-minsize', args.minsize, '-fastaout', sort_out], stdout = FNULL, stderr = FNULL)

#now run clustering algorithm
radius = str(100 - int(args.pct_otu))
otu_out = args.out + '.EE' + args.maxee + '.otus.fa'
log.info("Clustering OTUs (UPARSE)")
if args.size_annotations:
    log.debug("%s -cluster_otus %s -sizein -sizeout -relabel OTU_ -otu_radius_pct %s -otus %s" % (usearch, sort_out, radius, otu_out))
    subprocess.call([usearch, '-cluster_otus', sort_out, '-sizein', '-sizeout', '-relabel', 'OTU_', '-otu_radius_pct', radius, '-otus', otu_out], stdout = FNULL, stderr = FNULL)
else:
    log.debug("%s -cluster_otus %s -relabel OTU_ -otu_radius_pct %s -otus %s" % (usearch, sort_out, radius, otu_out))
    subprocess.call([usearch, '-cluster_otus', sort_out, '-relabel', 'OTU_', '-otu_radius_pct', radius, '-otus', otu_out], stdout = FNULL, stderr = FNULL)
total = countfasta(otu_out)
log.info('{0:,}'.format(total) + ' OTUs')

#clean up padded N's
log.info("Cleaning up padding from OTUs")
otu_clean = args.out + '.EE' + args.maxee + '.clean.otus.fa'
with open(otu_clean, 'w') as output:
    with open(otu_out, 'r') as input:
        for line in input:
            if line.startswith (">"):
                output.write(line)
            else:
                line = re.sub('[^GATC]', "", line)
                line = line + '\n'
                if line != '\n':
                    output.write(line)

#optional UCHIME Ref 
if args.uchime_ref == "False":
    uchime_out = otu_clean
else:
    uchime_out = args.out + '.EE' + args.maxee + '.uchime.otus.fa'
    #You might need to update these in the future, but leaving data and version in name so it is obvious where they came from
    if args.uchime_ref == "ITS1":
        uchime_db = os.path.join(script_path, 'lib', 'uchime_sh_refs_dynamic_develop_985_11.03.2015.ITS1.fasta')
    if args.uchime_ref == "ITS2":
        uchime_db = os.path.join(script_path, 'lib', 'uchime_sh_refs_dynamic_develop_985_11.03.2015.ITS2.fasta')
    if args.uchime_ref == "Full":
        uchime_db = os.path.join(script_path, 'lib', 'uchime_sh_refs_dynamic_original_985_11.03.2015.fasta')
    log.info("Chimera Filtering (UCHIME)")
    log.debug("%s -uchime_ref %s -strand plus -db %s -nonchimeras %s" % (usearch, otu_clean, uchime_db, uchime_out))
    subprocess.call([usearch, '-uchime_ref', otu_out, '-strand', 'plus', '-db', uchime_db, '-nonchimeras', uchime_out], stdout = FNULL, stderr = FNULL)
    total = countfasta(uchime_out)
    log.info('{0:,}'.format(total) + ' OTUs passed')

#option if using mock community to map OTUs to mock and add to header
if args.mock != "False":
    if args.mc == "ufits_mock3.fa":
        mock = os.path.join(script_path, 'lib', 'ufits_mock3.fa')
    else:
        mock = args.mc
    #count seqs in mock community
    mock_ref_count = countfasta(mock)
    
    #map OTUs to mock community
    mock_out = args.out + '.mockmap.uc'
    log.info("Mapping Mock Community (USEARCH8)")
    log.debug("%s -usearch_global %s -strand plus -id 0.97 -db %s -uc %s" % (usearch, uchime_out, mock, mock_out))
    subprocess.call([usearch, '-usearch_global', uchime_out, '-strand', 'plus', '-id', '0.97', '-db', mock, '-uc', mock_out], stdout = FNULL, stderr = FNULL)
    
    #generate dictionary for name change
    annotate_dict = {}
    with open(mock_out, 'r') as map:
        map_csv = csv.reader(map, delimiter='\t')
        for line in map_csv:
            if line[-1] != "*":
                annotate_dict[line[-2]]=line[-1] 
             
    otu_new = args.out + '.EE' + args.maxee + '.mock.otus.fa'
    otu_update = open(otu_new, "w")
    with open(uchime_out, "r") as myfasta:
        for line in myfasta:
            if line.startswith (">"):
                line = line[1:]
                line = line.split()
                if line[0] in annotate_dict:
                    new_line = ">" + "".join(annotate_dict[line[0]]+'\n')
                    otu_update.write (new_line)
                else:
                    otu_update.write (">"+ "".join(line) + "\n")
            else:
                otu_update.write(line)
    otu_update.close()
    uchime_out = otu_new
    
#now map reads back to OTUs
uc_out = args.out + '.EE' + args.maxee + '.mapping.uc'
if args.map_unfiltered:
    reads = args.FASTQ
else:
    reads = filter_out
log.info("Mapping Reads to OTUs (USEARCH8)")
log.debug("%s -usearch_global %s -strand plus -id 0.97 -db %s -uc %s" % (usearch, reads, uchime_out, uc_out))
subprocess.call([usearch, '-usearch_global', reads, '-strand', 'plus', '-id', '0.97', '-db', uchime_out, '-uc', uc_out], stdout = FNULL, stderr = FNULL)

#Build OTU table
otu_table = args.out + '.EE' + args.maxee + '.otu_table.txt'
uc2tab = os.path.join(script_path, 'lib', 'uc2otutable.py')
log.info("Creating OTU Table")
log.debug("%s %s %s" % (uc2tab, uc_out, otu_table))
subprocess.call([uc2tab, uc_out, otu_table], stdout = FNULL, stderr = FNULL)

if args.mock != "False":
    #first check if the name is in mock, if not don't run the stats
    with open(otu_table, 'r') as f:
        first_line = f.readline().strip()
        check = first_line.split('\t')
        if args.mock not in check:
            result = 'fail'
            log.info("%s not found in OTU table, skipping stats. (use ufits-mock_filter.py for stats)" % args.mock)
        else:
            result = 'pass'
            
#run some stats on mock community if --mock option passed.
if args.mock != "False" and result != 'fail':
    KEEP_COLUMNS = ('OTUId', args.mock)
    f = csv.reader(open(otu_table), delimiter='\t')
    headers = None
    results = []
    for row in f:
        if not headers:
            headers = []
            for i, col in enumerate(row):
                if col in KEEP_COLUMNS:
                    headers.append(i)
        else:
            results.append(tuple([row[i] for i in headers]))
    num_otus = 0
    mock_found = 0
    bad_otu = []
    good_otu = []
    for row in results:
        if int(row[1]) > 0:
            num_otus += 1
            if not "OTU" in row[0]:
                mock_found += 1
                good_otu.append(int(row[1]))
            if "OTU" in row[0]:
                bad_otu.append(int(row[1]))
    spurious = num_otus - mock_found
    total_good_reads = sum(good_otu)
    print "-------------------------------------------------------"
    print "Summarizing data for %s, Length: %s bp, Quality Trimming: EE %s, " % (args.out, args.length, args.maxee)
    print "-------------------------------------------------------"
    print "Theoretical OTUs in Mock:  %i" % (mock_ref_count)
    print "Total OTUs detected in %s:  %i" % (args.mock, num_otus)
    print "\nReal Mock OTUs found:  %i" % (mock_found)
    if mock_found != 0:
        good_otu = sorted(good_otu, key=int)
        print "Range of counts from Real OTUs:  %i - %i" % (good_otu[-1], good_otu[0])
        print "Lowest counts from Real OTUs:  %i, %i, %i" % (good_otu[0], good_otu[1], good_otu[2])
        print "Total number of reads in Real OTUs: %s" % (total_good_reads)
    print "\nSpurious OTUs found:  %i" % (spurious)
    if spurious != 0:
        bad_otu = sorted(bad_otu, key=int, reverse=True)
        total_bad_reads = sum(bad_otu)
        print "Range of counts from Spurious OTUs:  %i - %i" % (bad_otu[0], bad_otu[-1])
        if spurious >= 3:
            print "Highest counts from Spurious OTUs:  %i, %i, %i" % (bad_otu[0], bad_otu[1], bad_otu[2])
        if spurious == 2:
            print "Highest counts from Spurious OTUs:  %i, %i" % (bad_otu[0], bad_otu[1])
        if spurious == 1:
            print "Highest count from Spurious OTUs:  %i" % (bad_otu[0])
        print "Total number of reads in Spurious OTUs: %s" % (total_bad_reads)
    os.remove(mock_out)

#Print location of files to STDOUT
print "-------------------------------------------------------"
print "OTU Clustering Script has Finished Successfully"
print "-------------------------------------------------------"
print ("Input FASTQ:           %s" % (args.FASTQ))
print ("Filtered FASTQ:        %s" % (filter_out))
print ("Dereplicated FASTA:    %s" % (derep_out))
print ("Sorted FASTA:          %s" % (sort_out))
print ("Clustered OTUs:        %s" % (otu_clean))
if args.uchime_ref != "False":
    print ("Chimera Filtered OTUs: %s" % (uchime_out))
print ("UCLUST Mapping file:   %s" % (uc_out))
print ("OTU Table:             %s" % (otu_table))
print ("USEARCH LogFile:       %s.log" % (args.out))
print "-------------------------------------------------------"

 