# coding: utf-8
import re,copy,sys,commands,hashlib

def main():
	vtc  = VarnishTest()
	argv = sys.argv
	argc = len(argv)
	opt  = ''
	if(argv == 1):
		exit
		
	opt = ' '.join(argv[1:])
	r= vtc.execVarnishTest(opt)
	if(r[0]['result'] != 'passed'):
		exit(1)

class VarnishTest:
	# regexp
	rfmt = 0
	rexp = 0
	
	# vtc command
	vtc  = 'varnishtest'
	
	nowSock = {
		'client'	:'',
		'server'	:'',
	}
	nowHTTP = {
		'client'	:{},
		'server'	:{},
	}
	# 関数リスト
	#  vtcfunc['comptype']['subcomp']
	vtcfunc = {
		'varnishtest':{},
		'server'     :{},
		'varnish'    :{},
		'client'     :{}
		}
	#filter
	filterFunc      = {}
	afterFilterFunc = {}
	event = {
		'varnishtest':{
#			'completed'       : 'Test completed',
			'sema'            : 'Semaphore sync',
			'delaying'        : 'Sleep',
			},
		'server'     :{
			'sema'            : 'Semaphore sync',
			'Starting server' : 'Starting server %comp%',
			'Started on '     : 'Started server %comp%',
			'accepted fd '    : 'Accepted Request %comp% <- todo(write sock)',
			'Ending'          : 'End server %comp%',
			},
		'varnish'    :{
			'Launch'          : 'Launch varnish %comp%',
			'Start'           : 'Start child process %comp%',
			'wait-running'    : 'Wait running %comp%',
			'stop'            : 'Stop varnish %comp%',
			'Stopping Child'  : 'Stop varnish child process %comp%',
			'delaying'        : 'Sleep',
			},
		'client'     :{
			'sema'            : 'Semaphore sync',
			'rxresp'          : 'Return response %comp%',
			'Starting client' : 'Starting client %comp%',
			'Connect to '     : 'Connecting %comp% -> todo(write sock)',
			'connected fd '   : 'Send Request %comp% -> todo(write sock)',
			'Ending'          : 'End client %comp%',
			'delaying'        : 'Sleep',
			}
	}
	
#---------------------------------------------------------------------------------------------------
	def __init__(self):
		#regex compile
		self.rfmt = re.compile('^([-*#]+) +([^ ]+) +([^ ]+) +([^|]+\|)?(.*)$')
		
		# req.url (/) == / (/) match
		# req.url (/) == /a (/a) failed
		self.rexp = re.compile('([^ ]+) \((.*)\) ([=!><]{1,2}) (.*) \((.*)\) (match|failed)')

		#filter
		self.filterFunc['varnish']               = self.filterVarnish
		self.filterFunc['client']                = self.filterClient
		self.filterFunc['server']                = self.filterServer
		self.filterFunc['varnishtest']           = self.filterVarnishtest

		#after filter
		self.afterFilterFunc['client']           = self.afterFilterClient

		#global
		self.vtcfunc['varnishtest']['macro def'] = self.conMacro
		self.vtcfunc['server']['macro def']      = self.conMacro
		self.vtcfunc['varnish']['macro def']     = self.conMacro
		self.vtcfunc['client']['macro def']      = self.conMacro

		self.vtcfunc['varnishtest']['EXPECT']    = self.conExpect
		self.vtcfunc['server']['EXPECT']         = self.conExpect
		self.vtcfunc['varnish']['EXPECT']        = self.conExpect
		self.vtcfunc['client']['EXPECT']         = self.conExpect
		
		#varnish
		self.vtcfunc['varnish']['CLI RX']        = self.renameVarnishCLI
		self.vtcfunc['varnish']['CLI RX:RES']    = self.renameVarnishCLI
		self.vtcfunc['varnish']['CLI TX']        = self.renameVarnishCLI

		#client

		#server

	
	# イベント解析のメインループ
	def constructEvent(self, data):
		i = -1
		data['event']     = []
		for v in data['line']:
			comptype = v['comptype']
			msg      = v['msg']
			tmp = self.event[comptype].items()
			for mpat, val in tmp:
				if msg.lstrip().startswith(mpat):
					i += 1
					data['event'].append(self.replaceStr(v,val))
			v['event'] = i

	
	# 構造作成のメインループ
	def constructData(self, data):
		idx  = 0
		skip = 0
		for v in data['line']:
			if skip > 0:
				skip -= 1
				idx  += 1
				continue
			comptype = v['comptype']
			subcomp  = v['subcomp']
			if subcomp in self.vtcfunc[comptype]:
				skip = self.vtcfunc[comptype][subcomp](v, data, idx)
			idx += 1
			

	# VarnishCLIのまとめ
	def renameVarnishCLI(self, data, ret, idx):
		if data['subcomp'] == 'CLI RX':
			data['aliassubcomp'] =  'CLI:' + data['comp'] + ' <- ' +  data['comp']
		elif data['subcomp'] == 'CLI RX:RES':
			data['aliassubcomp'] =  'CLI:' + data['comp'] + ' <- ' +  data['comp'] + "(Result)"
		else:
			data['aliassubcomp'] =  'CLI:' + data['comp'] + ' -> ' +  data['comp']
		return 0
	
	# EXPECTのまとめ
	def conExpect(self, data, ret, idx):
		if not 'expect' in ret:
			ret['expect'] = []
		#   1      2   3 4  5   6
		# req.url (/) == / (/) match
		# @@
		skip = 0
		m = self.rexp.search(data['msg'])
		if not m:
			#複数行パタン
			cnt = len(ret['line'])
			nc  = idx + 1
			while nc < cnt:
				if not ret['line'][nc]['comp'] == 'shell':
					return 0
				skip += 1
				data['msg'] = data['msg'] + '<RETURN>' + ret['line'][nc]['msg']
				m = self.rexp.search(data['msg'])
				if m:
					break
				nc += 1
		
		tmp = {
			'comp'     : data['comp'],
			's1_key'   : m.group(1),
			's1_val'   : m.group(2),
			'operator' : m.group(3),
			's2_key'   : m.group(4),
			's2_val'   : m.group(5),
			'result'   : m.group(6),
			}
		if data.has_key('httpdata'):
			tmp['httpdata'] = data['httpdata']
		ret['expect'].append(tmp)
		return skip
	
	def mergeExpect(self, ret):
		if not ret.has_key('expect'):
			return
		ret['mergeExpect'] = {}
		for v in ret['expect']:
			#gen hash
			httpdata = str(v['httpdata']['length'])
			for vv in v['httpdata']['body']:
				httpdata += vv
			for vv in v['httpdata']['head']:
				httpdata += vv
			key = hashlib.md5(httpdata).hexdigest()
			
			if not ret['mergeExpect'].has_key(key):
				ret['mergeExpect'][key] = {}
				ret['mergeExpect'][key]['httpdata'] = v['httpdata']
				ret['mergeExpect'][key]['expect']   = []
				ret['mergeExpect'][key]['comp']     = v['comp']
			
			ret['mergeExpect'][key]['expect'].append({
				'operator' : v['operator'],
				'result'   : v['result'],
				's1_key'   : v['s1_key'],
				's1_val'   : v['s1_val'],
				's2_key'   : v['s2_key'],
				's2_val'   : v['s2_val'],
				})
		
	#マクロ定義を作成
	def conMacro(self, data, ret, idx):
		if not 'macro' in ret:
			ret['macro'] = {}
		tmp = data['msg'].split('=', 2)
		ret['macro'][tmp[0]] = tmp[1]
		return 0

	
	def parseLine(self, line, idx = 0):
		# sucess line
		# # top TEST example.vtc passed (0.498)
		# 1  2   3   4

		# error line
		# **** top   0.0 macro def varnishd=varnishd
		# 1    2     3   4
		ret = {
				'seq'     : idx , # sequence idx
				'event'   : -1  , # eventid
				'type'    : 0   , # 0=sucess 1=error
				'lv'      : 0   , # log level
				'comptype':''   , # compornent type
				'comp'    : ''  , # compornent
				'subcomp' : ''  , # sub compornent
				'time'    : 0.0 , # time
				'msg'     : ''  , # message
				'raw'     : ''    # rawdata
			}
		
		m = self.rfmt.search(line)
		ret['raw'] = line
		if not m:
			######## varnish-3.0.3/bin/varnishtest/tests/a00009.vtc ########
			if line.startswith("######## "):
				ret['comp'] = 'top'
				ret['msg']  = line
			else:
				#shell exec?後で確認
				ret['comp'] = 'shell'
				ret['msg']  = line
		elif m.group(1) == '#':
			#sucess
			if m.group(3) == 'TEST':
				##     top  TEST test.vtc passed (0.474)
				##     top  TEST varnish-3.0.3/bin/varnishtest/tests/a00009.vtc FAILED (0.002) exit=1
				if -1 == line.find(' passed'):
					spl = m.group(5).split(' ')
					ret['comp'] = m.group(2)
					ret['subcomp'] = 'TEST'
					ret['msg']  = spl[0] + ' ' + spl[3] + ' ' + spl[1]
					ret['time'] = float(spl[2].strip('()'))
				else:
					spl = m.group(5).split(' ')
					ret['subcomp'] = 'TEST'
					ret['comp'] = m.group(2)
					ret['msg']  = spl[0] + ' ' + spl[1]
					ret['time'] = float(spl[2].strip('()'))
			else:
				spl = m.group(5).split(' ')
				ret['comp'] = m.group(2)
				ret['msg']  = m.group(5) + ' ' + spl[0] + ' ' + spl[1]
				ret['time'] = float(spl[2].strip('()'))
		else:
			#error
			if m.group(1)[0] != '-':
				ret['lv'] = len(m.group(1))
			else:
				ret['type'] = 1
			ret['comp'] = m.group(2)
			ret['time'] = float(m.group(3))
			ret['msg']  = m.group(5)
			if m.group(4):
				ret['subcomp']  = m.group(4).rstrip('|')
			else:
				self.SubComp(ret)
			
		self.compType(ret)
		return ret;
	#コンポーネントタイプを判定
	def compType(self, data):
		if data['comp'][0] == 'v':
			data['comptype'] = 'varnish'
		elif data['comp'][0] == 'c':
			data['comptype'] = 'client'
		elif data['comp'][0] == 's':
			data['comptype'] = 'server'
		elif data['comp']    == 'top':
			data['comptype'] = 'varnishtest'

	def SubComp(self, data):
		#macro
		if data['msg'].startswith('macro def '):
			data['msg']     = data['msg'][10:]
			data['subcomp'] = 'macro def'
		elif data['msg'].startswith('macro undef '):
			data['msg']     = data['msg'][12:]
			data['subcomp'] = 'macro undef'
		elif data['msg'].startswith('EXPECT '):
			data['msg']     = data['msg'][7:]
			data['subcomp'] = 'EXPECT'



	def splitData(self,r):
		ret = []
		st = 0
		ed = 0
		for v in r['line']:
			ed += 1
			if v['comptype'] == 'varnishtest':
				 if v['msg'].endswith(' passed') or (not v['raw'].endswith(' FAILED') and v['msg'].endswith(' FAILED')):
				 	ret.append({'line':r['line'][st:st + ed]})
				 	st = st + ed
				 	ed = 0
		return ret

	############################
	#Filter functions
	############################

	
	# varnishtestのフィルタ
	def filterVarnishtest(self, data, ret):
		#  | top |                | test.vtc passed (0.504) test.vtc passed
		#  | top |                | test.vtc FAILED (1.434) exit=1 test.vtc FAILED
		if data['msg'].startswith('TEST '):
			data['subcomp'] = 'TEST'
			data['msg']     = data['msg'].replace('TEST ','')
		
		if data['type'] == 1:
			self.addError("[" + data['comp'] + "] "+ data['msg'], ret)

		if data['msg'].endswith(' passed'):
			ret['result']   = 'passed'
			ret['vtcname']  = data['msg'].split(' ',2)[0]
		elif data['msg'].endswith(' FAILED'):
			ret['result']   = 'FAILED'
			ret['vtcname']  = data['msg'].split(' ',2)[0]
		elif data['msg'].startswith('Unknown command: '):
			#self.addError(data['msg'].replace('Unknown command','Unknown command(VTCSyntaxError)'), ret)
			data['subcomp'] = 'Unknown command(VTCSyntaxError)'
			data['msg']     = data['msg'].replace('Unknown command: ','')


	# Serverのフィルタ
	def filterServer(self, data, ret):
		if data['msg'].startswith('bodylen = '):
			data['subcomp'] = 'bodylen'
			data['msg'] = data['msg'].replace('bodylen = ','')
			self.nowHTTP['server']['length'] = int(data['msg'])
		elif data['subcomp'].startswith('http[ 0]'):
			self.nowHTTP['server'] = {'head':[],'body':[],'length':0}
			self.nowHTTP['server']['head'].append(data['msg'][1:])
		elif data['subcomp'].startswith('http['):
			self.nowHTTP['server']['head'].append(data['msg'][1:])
		elif data['subcomp'] == 'body':
			self.nowHTTP['server']['body'].append(data['msg'][1:])
		elif data['subcomp'] == 'EXPECT':
			data['httpdata'] = copy.deepcopy(self.nowHTTP['server'])
		if data['type'] == 1:
			self.addError("[" + data['comp'] + "] "+ data['msg'], ret)


	# Clientのフィルタ
	def filterClient(self, data, ret):
		if data['msg'].startswith('bodylen = '):
			data['subcomp'] = 'bodylen'
			data['msg'] = data['msg'].replace('bodylen = ','')
			self.nowHTTP['client']['length'] = int(data['msg'])
		elif data['subcomp'].startswith('http[ 0]'):
			self.nowHTTP['client'] = {'head':[],'body':[],'length':0}
			self.nowHTTP['client']['head'].append(data['msg'][1:])
		elif data['subcomp'].startswith('http['):
			self.nowHTTP['client']['head'].append(data['msg'][1:])
		elif data['subcomp'] == 'body':
			self.nowHTTP['client']['body'].append(data['msg'][1:])
		elif data['subcomp'] == 'EXPECT':
			data['httpdata'] = copy.deepcopy(self.nowHTTP['client'])
		if data['type'] == 1:
			self.addError("[" + data['comp'] + "] "+ data['msg'], ret)

	# Varnishのフィルタ
	def filterVarnish(self, data, ret):
		if data['msg'].startswith('CLI RX '):
			data['subcomp'] = 'CLI RX:RES'
			data['msg'] = data['msg'].replace('CLI RX ','')
		if data['type'] == 1:
			self.addError("[" + data['comp'] + "] "+ data['msg'], ret)
	
	# データ正規化用フィルタ
	def filterData(self, data):
		for v in data['line']:
			comptype = v['comptype']
			if self.filterFunc.has_key(comptype):
				self.filterFunc[comptype](v, data)

	############################
	#Filter functions(After)
	############################

	# Clienthのフィルタ
	def afterFilterClient(self, data, ret):
		#開いてるソケット情報
		#  | c1 |       | connected fd 10 from 127.0.0.1 48351 to 127.0.0.1 34994
		
		if data['msg'].startswith('connected fd '):
			for k, v in ret['macro'].items():
				if k.endswith('_sock'):
					if data['msg'].endswith(v):
						self.nowSock['client'] = k.replace('_sock','')
		elif data['subcomp'].startswith('rx'):
			data['aliassubcomp'] = data['subcomp'] + ':' + data['comp'] + ' <- ' + self.nowSock['client']
		elif data['subcomp'].startswith('tx'):
			data['aliassubcomp'] = data['subcomp'] + ':' + data['comp'] + ' -> ' + self.nowSock['client']


	# データ正規化用フィルタ
	def afterFilterData(self, data):
		for v in data['line']:
			comptype = v['comptype']
			if self.afterFilterFunc.has_key(comptype):
				self.afterFilterFunc[comptype](v, data)


	############################
	#Util functions
	############################

	# 文字列置換用
	def replaceStr(self, dat, text):
		tmp = dat.items()
		for k,v in tmp:
			text = text.replace(str('%' + k + '%'), str(v))
		return text

	def chkMaxLength(self, val ,init = 0):
		i = init
		for v in val:
			lv = len(v)
			if lv > i:
				i = lv
		return i

	def pad(self, max, str, pad = ' '):
		return pad * (max - len(str))

	def addError(self,msg, ret):
		if not ret.has_key('error'):
			ret['error'] = []
		ret['error'].append(msg)

	def parseVTC(self, txt):
		if not re.search('^[-*#]',txt):
			return {'mode':'cmd','data':txt}
		r   = txt.splitlines()
		
		i = 0
		ret = {'mode':'vtc','line':[]}
		for v in r:
			if v == '':
				continue
			i+=1
			ret['line'].append(self.parseLine(v, i))
		
		return ret

	#exec varnishtest
	def runVTC(self, opt):
		return commands.getoutput(self.vtc + ' ' + opt)


	############################
	#Complex functions
	############################

	def execVarnishTest(self, opt):
		if not -1 == opt.find('-S'):
			#STDINから読み込む
			r= self.parseVTC('\n'.join(sys.stdin.readlines()))
		else:
			#vtc実行
			r= self.parseVTC(self.runVTC(opt))
		
		if r['mode'] == 'cmd':
			print r['data']
			return

		#データの分割
		r = self.splitData(r)
		for v in r:
			#データの正規化
			self.filterData(v)
			#データの作成
			self.constructData(v)
			#データの正規化
			self.afterFilterData(v)
			#イベントデータの作成
			self.constructEvent(v)
			#expectデータのマージ
			self.mergeExpect(v)
			
			#出力
			self.printVTC(v)
		return r

	def printVTC(self, r):
		self.printLine('<')
		print r['vtcname']
		self.printMainLine(r)
		if r.has_key('macro'):
			self.printMacro(r)
			self.printExpect(r)
		self.printError(r)
		self.printResult(r)
		self.printLine('>')
		print

	############################
	#Print functions
	############################

	def printError(self,r):
		if not r.has_key('error'):
			return
		self.printLine('#')
		print 'Error list'
		self.printLine()
		for v in r['error']:
			print v
		print 

	def printLine(self, char = '-' ,length = 70):
		print char * length

	def printLineGlue(self, idx, char = '-', glue = '+', length = 70):
		length -= 1
		print char * idx + glue + '-' * (length - idx)
		
	def printMainLine(self, data):
		self.printLine('-')
		print("<<<< Test start >>>>")
		
		#iline  = data['line']
		#event = data['event']
		nowEvent = -1

		evMaxComp    = {-1:0}
		evMaxSubComp = {-1:0}

		for v in data['line']:
			evi = v['event']
			if not evMaxComp.has_key(evi):
				evMaxComp[evi]    = 0
				evMaxSubComp[evi] = 0

			lengthComp    = len(v['comp'])
			if v.has_key('aliassubcomp'):
				lengthSubComp = len(v['aliassubcomp'])
			else:
				lengthSubComp = len(v['subcomp'])
			if evMaxComp[evi] < lengthComp:
				evMaxComp[evi] = lengthComp

			if evMaxSubComp[evi] < lengthSubComp:
				evMaxSubComp[evi] = lengthSubComp

		
		for v in data['line']:
			if nowEvent < v['event']:
				#self.printLine('-')
				nowEvent = v['event']
				print '\n<<<< ',
				print(data['event'][nowEvent]),
				print ' >>>>'

			subcomp = ''
			if v.has_key('aliassubcomp'):
				subcomp = v['aliassubcomp']
			else:
				subcomp = v['subcomp']
			
			sc  = ' ' * (evMaxComp[nowEvent] - len(v['comp']))
			ssc = ' ' * (evMaxSubComp[nowEvent] - len(subcomp))
			print v['raw']
			'''
			print "  | %s%s | %s%s | %s" % (
				v['comp'],
				sc,
				subcomp,
				ssc,
				v['msg'],
				
				)
			'''
		print

	
	def printKV(self, dic, title = '' , desc = '' , dmt = '|', mgn = 2):
		items = dic.items()
		init  = 0
		if title != '':
			init = len(title)
		max   = self.chkMaxLength(dic.keys(), init)
		
		
		if title != '':
			print title + self.pad(max,title) + (' ' * mgn) + dmt + (' ' * mgn) + desc
			self.printLineGlue(max + mgn)
		for k, v in items:
			print k + self.pad(max,k) + (' ' * mgn) + dmt + (' ' * mgn) + v
		
	
	def printMacro(self, data):
		self.printLine('#')
		print 'Macro list'
		self.printLine()
		self.printKV(data['macro'], '[key]', '[value]')
		print


	def printResult(self, data):
		self.printLine('#')
		print 'VTC result'
		print '  | ' + data['result'] + ' | ' + data ['vtcname']
		self.printLine()

		#length =  len(data ['vtcname']) + len(data['result']) + 4
		#print ' '* 10 + ' -'+ '-' * length + '-'
		#print ' '* 10 + '| '+  data ['vtcname'] +' is '+ data['result'] + ' |'
		#print ' '* 10 + ' -'+ '-' * length + '-'
	
	def printExpect(self, data):
		if not data.has_key('mergeExpect'):
			return
		'''
			----------------------------------------------------------------------
			c2 expect
			----------------------------------------------------------------------
			HTTP:header     | HTTP/1.1
			                | 200
			                | Ok
			                | Cache-control: max-age = 1
			                | Connection: keep-alive
			HTTP:body       | 22222\n
			HTTP:bodylen    | 6
			                |
			expr[1]         | resp.http.content-length == 6
			expr[1](val)    | 6 == 6
			expr[1](result) | match
			                |
			expr[2]         | resp.http.content-length == 6
			expr[2](val)    | 6 == 6
			expr[2](result) | match
			----------------------------------------------------------------------
		'''
		self.printLine('#')
		print 'Expect list'
		self.printLine()

		for k,v in data['mergeExpect'].items():
			print v['comp'] + ' expect (' + k + ')'
			self.printLine()

			#print http header body length
			length = len(str(len(v['httpdata']['head']))) + len('EXPECT[]:result')

			if len(v['httpdata']['head']) > 0:
				print 'HTTP:header' + (length - len('HTTP:header')) * ' ' + ' |' + '-' * 40
				for vv in v['httpdata']['head']:
					print length * ' ' + ' | ' + vv
			if len(v['httpdata']['body']) > 0:
				print 'HTTP:body' + (length - len('HTTP:body')) * ' ' + ' |' + '-' * 40
				for vv in v['httpdata']['body']:
					print length * ' ' + ' | ' + vv
			print 'HTTP:bodylen' + (length - len('HTTP:bodylen')) * ' ' + ' |' + '-' * 40
			print length * ' ' + ' | ' + str(v['httpdata']['length'])

			#print expect
			i = 0
			for vv in v['expect']:
				km = 'EXPECT[' + str(i) + ']'
				print km  + (length - len(km)) * ' ' + ' |' + '-' * 40
				print km + ':expr' + (length - len(km + ':expr')) * ' ' + ' | ' + vv['s1_key'] + " " + vv['operator'] + " " + vv['s2_key']
				print km + ':val' + (length - len(km + ':val')) * ' ' + ' | ' + vv['s1_val'] + " " + vv['operator'] + " " + vv['s2_val']
				print km + ':result' + (length - len(km + ':result')) * ' ' + ' | ' + vv['result']
				i += 1
			self.printLine()
		'''
		maxComp = len('[compornent]')
		maxRes  = len('HTTP:bodylen')
		exp = data['expect']
		for v in exp:
			lt = len(v['comp'])
			if(maxComp < lt):
				maxComp = lt
			lt = len(v['result'])
			if(maxRes < lt):
				maxRes = lt

		fmt  = "%- "+str(maxComp)+"s | %- "+str(maxRes)+"s | %s %s %s"

		print fmt  % ('[compornent]', '[result]', '[data]','','')
		self.printLine()
		for v in exp:
			print fmt  % (v['comp'], 'result', v['result'],'','')
			print fmt  % ('', '', '','','')
			if v.has_key('httpdata'):
				for vv in v['httpdata']['head']:
					print fmt  % ('', 'HTTP:header', vv,'','')
				for vv in v['httpdata']['body']:
					print fmt  % ('', 'HTTP:body', vv,'','')
				print fmt  % ('', 'HTTP:bodylen', v['httpdata']['length'],'','')
			
			print fmt  % ('', 'expr', v['s1_key'], v['operator'], v['s2_key'])
			print fmt  % ('', 'expr(val)', v['s1_val'], v['operator'], v['s2_val'])
			self.printLine()
		print
		'''

#---------------------------------------------------------------------------------------------------
# ref:http://tomoemon.hateblo.jp/entry/20090921/p1
from pprint import pprint
import types

def var_dump(obj):
  pprint(dump(obj))

def dump(obj):
  '''return a printable representation of an object for debugging'''
  newobj = obj
  if isinstance(obj, list):
    # リストの中身を表示できる形式にする
    newobj = []
    for item in obj:
      newobj.append(dump(item))
  elif isinstance(obj, tuple):
    # タプルの中身を表示できる形式にする
    temp = []
    for item in obj:
      temp.append(dump(item))
    newobj = tuple(temp)
  elif isinstance(obj, set):
    # セットの中身を表示できる形式にする
    temp = []
    for item in obj:
      # itemがclassの場合はdump()は辞書を返すが,辞書はsetで使用できないので文字列にする
      temp.append(str(dump(item)))
    newobj = set(temp)
  elif isinstance(obj, dict):
    # 辞書の中身（キー、値）を表示できる形式にする
    newobj = {}
    for key, value in obj.items():
      # keyがclassの場合はdump()はdictを返すが,dictはキーになれないので文字列にする
      newobj[str(dump(key))] = dump(value)
  elif isinstance(obj, types.FunctionType):
    # 関数を表示できる形式にする
    newobj = repr(obj)
  elif '__dict__' in dir(obj):
    # 新しい形式のクラス class Hoge(object)のインスタンスは__dict__を持っている
    newobj = obj.__dict__.copy()
    if ' object at ' in str(obj) and not '__type__' in newobj:
      newobj['__type__']=str(obj).replace(" object at ", " #").replace("__main__.", "")
    for attr in newobj:
      newobj[attr]=dump(newobj[attr])
  return newobj

#---------------------------------------------------------------------------------------------------

main()
