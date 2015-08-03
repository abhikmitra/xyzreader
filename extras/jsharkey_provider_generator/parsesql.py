#!/usr/bin/python

'''
    Copyright 2010, The Android Open Source Project

    Licensed under the Apache License, Version 2.0 (the "License"); 
    you may not use this file except in compliance with the License. 
    You may obtain a copy of the License at 

        http://www.apache.org/licenses/LICENSE-2.0 

    Unless required by applicable law or agreed to in writing, software 
    distributed under the License is distributed on an "AS IS" BASIS, 
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. 
    See the License for the specific language governing permissions and 
    limitations under the License.
'''

# script to autogenerate contentprovider from annotated sql
# written by jeff sharkey, http://jsharkey.org/

import re, string
import sys

INPUTSQL = sys.argv[1]

TABLE = re.compile(r"(?:/\*\*(?P<comment>[^;]+?)\*/)?\s*CREATE TABLE (?P<name>.+?) (?P<body>\(.+?\);)", re.S)
VIEW = re.compile(r"(?:/\*\*(?P<comment>[^;]+?)\*/)?\s*CREATE VIEW (?P<name>.+?) (?P<body>.+?);", re.S)
COLUMN = re.compile(r"(?<=[,\(])\s*(?:/\*\*(?P<comment>.+?)\*/)?\s*(?P<columnname>.+?)\s+(?P<columndef>.+?)(?=,\n|\n\);)", re.S)
PARAM = re.compile(r"\{@(?P<keyword>.+?)(?P<param1> .+?)?(?P<param2> .+?)?\}", re.S)
HEADER = re.compile(r"\/*\n(?P<header>.+?)\n*\/", re.S)

def java_name(name):
	words = name.split("_")
	return "".join( [ word[0].upper() + word[1:] for word in words ] )


class Table:
	def __init__(self, values):
		self.name = values['name']
		
		# find params and columns
		self.params = [ match.groupdict() for match in PARAM.finditer(values['comment']) ]
		self.columns = [ match.groupdict() for match in COLUMN.finditer(values['body']) ]
		
		self.exportAs = None
		self.queryWith = None
		self.match = []
		
		for param in self.params:
			if param['keyword'] == "exportAs":
				self.exportAs = param['param1'].strip()
			elif param['keyword'] == "queryWith":
				self.queryWith = param['param1'].strip()
			elif param['keyword'] == "matchDir" or param['keyword'] == "matchItem":
				self.match.append(param)
		
		print "CREATE TABLE %s (%d params, %d columns)" % (self.name, len(self.params), len(self.columns))
	
	def __repr__(self):
		return self.name

	def dump_match(self, into):
		for match in self.match:
			into.append( (match, self) )

	def contract_columns(self):
		if self.exportAs == None: return ""
		body = ""
		for c in self.columns:
			coltype = c['columndef']
			if c['comment'] is not None:
				comment = c['comment'].strip()
				if comment[-1] != ".": comment += "."
				body += "\t/** %s Type: %s */\n" % (comment, coltype)
			else:
				body += "\t/** Type: %s */\n" % (coltype)
			
			body += """\tString %s = "%s";\n""" % (c['columnname'].upper(),c['columnname'])
		return "\ninterface %sColumns {\n%s}" % (self.exportAs, body)

	def contract_builder_method(self, matchtype, pattern, target):

		if target is None: target = ""
		else:
			target = target.strip()
			if len(target) > 0 and target[0] == "#":
				target = target.strip()[1:]
			else: raise Exception("expected #Target")

		if matchtype == "matchDir":	methodname = "build%sDirUri" % (target)
		else: methodname = "build%sItemUri" % (target)
		
		# TODO: match against column type to find java param type
		params = [ param for param in pattern.split("/") if len(param) > 0 ]
		methodparams = [ param[1:-1] for param in params if param[0] == "[" and param[-1] == "]" ]
		methodparams = ", ".join( [ "long %s" % (param) for param in methodparams ] )
		
		builder = ""
		for param in params:
			if param[0] == "[" and param[-1] == "]":
				builder += ".appendPath(Long.toString(%s))" % (param[1:-1])
			else:
				builder += """.appendPath("%s")""" % (param)
		
		return """
	/** Matches: %s */
	public static Uri %s(%s) {
		return BASE_URI.buildUpon()%s.build();
	}
""" % (pattern, methodname, methodparams, builder)

	def contract_body(self):
		if self.exportAs == None: return ""
		mimetypes = """
	public static final String CONTENT_TYPE = "vnd.android.cursor.dir/vnd.%s.%s";
	public static final String CONTENT_ITEM_TYPE = "vnd.android.cursor.item/vnd.%s.%s";
""" % (PACKAGE, self.name, PACKAGE, self.name)
		
		builders = ""
		for match in self.match:
			matchtype = match['keyword']
			pattern = match['param1'].strip()
			target = match['param2']
			builders += self.contract_builder_method(matchtype, pattern, target)

		return """public static class %s implements %sColumns {%s%s}""" % (self.exportAs, self.exportAs, mimetypes, builders)

	def contract(self):
		if self.exportAs == None: return ""
		return "%s\n\n%s" % (self.contract_columns(), self.contract_body())
		
class View:
	def __init__(self, values):
		self.name = values['name']
		
		# find params
		self.params = [ match.groupdict() for match in PARAM.finditer(values['comment']) ]
		
		self.exportAs = None
		self.contains = []
		self.match = []
		
		for param in self.params:
			if param['keyword'] == "exportAs":
				self.exportAs = param['param1'].strip()
			elif param['keyword'] == "contains":
				self.contains.append(param['param1'].strip())
			elif param['keyword'] == "matchDir" or param['keyword'] == "matchItem":
				self.match.append(param)
		
		print "CREATE VIEW %s (%d params)" % (self.name, len(self.params))
	
	def __repr__(self):
		return self.name
	
	def dump_match(self, into):
		for match in self.match:
			into.append( (match, self) )

	def contract(self):
		params = {}
		params['class'] = self.exportAs
		params['columnsClass'] = "%sColumns" % (self.exportAs)
		params['containsClause'] = ", ".join([ "%sColumns" % (table) for table in self.contains ])
		# TODO: enforce that contains actually are valid tables
		
		return string.Template("""
interface ${columnsClass} extends ${containsClause} {
}

public static class ${class} implements ${columnsClass} {
}""").substitute(params)


def contract():
	params = {}
	params['package'] = PACKAGE
	params['contractClass'] = "%sContract" % (TARGETNAME)
	
	params['tables'] = "\n".join( [ table.contract() for table in TABLES_LIST ] ).replace("\n","\n\t")
	params['views'] = "\n".join( [ view.contract() for view in VIEWS_LIST ] ).replace("\n","\n\t")
	
	return string.Template("""package ${package};

import android.net.Uri;

public class ${contractClass} {
	public static final String CONTENT_AUTHORITY = "${package}";
	public static final Uri BASE_URI = Uri.parse("content://${package}");
${tables}
${views}

	private ${contractClass}() {
	}
}
""").substitute(params)
 


def provider():

	params = {}
	params['package'] = PACKAGE

	params['contractClass'] = "%sContract" % (TARGETNAME)
	params['providerClass'] = "Abstract%sProvider" % (TARGETNAME)

	params['tableNames'] = "\n".join( [ """\t\tString %s = "%s";""" % (table.name.upper(), table.name) for table in TABLES_LIST ] )
	params['viewNames'] = "\n".join( [ """\t\tString %s = "%s";""" % (view.name.upper(), view.name) for view in VIEWS_LIST ] )
	
	# collect all matches
	matchers = []
	for table in TABLES_LIST: table.dump_match(matchers)
	for view in VIEWS_LIST: view.dump_match(matchers)
	
	constants = []; builders = []; typecases = []; insertcases = [];
	querySelectionCases = []; selectionCases = [];
	
	reclean = re.compile("[^A-Za-z0-9-_/]")
	retarget = re.compile("\[.+?\]")
	for match in matchers:
		match, target = match
		path = match['param1'].strip().strip("/")
		
		constant = reclean.sub("", path).replace("/", "_").upper()
		constants.append("""\tprivate static final int %s = %s;""" % (constant, len(constants)))
		
		# TODO: lookup against table to find column type for */#
		builder = retarget.sub("#", path)
		builders.append("""\t\tmatcher.addURI(authority, "%s", %s);""" % (builder, constant) )

		# find normal target table
		targetTable = target.exportAs
		if match['param2'] is not None:
			targetTable = match['param2'].strip().strip("#")
		
		# when pointed to specific view, dump queries into specific bucket
		# otherwise when no view, just use regular selection builder bucket
		queryWithView = None
		if isinstance(target, View):
			queryWithView = target.exportAs
		elif isinstance(target, Table) and target.queryWith is not None:
			queryWithView = target.queryWith

		# build record of paths that require vars
		count = 0; varsextract = []; varsbuilder = [];
		for param in path.split("/"):
			if param[0] == "[" and param[-1] == "]":
				col = param[1:-1]
				varsextract.append( (col, count) )
				varsbuilder.append( (target.exportAs, col.upper(), col) )
			count += 1

		varsextract = "".join([ """\n\t\t\t\tfinal String %s = paths.get(%d);""" % var for var in varsextract ])
		varsbuilder = "".join([ """.where(%s.%s + "=?", %s)""" % var for var in varsbuilder ])

		if match['keyword'] == "matchDir":
			typecases.append("\t\t\tcase %s:\n\t\t\t\treturn %s.CONTENT_TYPE;" % (constant, targetTable))
			
			# inserts only happen into dirs
			# TODO: handle inserts into dirs that contain params in uri (usually m*n)
			hasparams = path.find("[") != -1
			if isinstance(target, Table) and not hasparams:
				insertcases.append("""
			case %s: {
				final long _id = db.insertOrThrow(Tables.%s, null, values);
				return %s.buildItemUri(_id);
			}""" % (constant, target.name.upper(), targetTable))
			
			# when table, build normal query string
			if isinstance(target, Table):
				selectionCases.append("""
			case %s: {%s
				return builder.table(Tables.%s)%s;
			}""" % (constant, varsextract, target.name.upper(), varsbuilder))
			
			# when view, or table with queryWith, build separate query
			if queryWithView is not None:
				view = VIEWS_EXPORTED[queryWithView]
				querySelectionCases.append("""
			case %s: {%s
				return builder.table(Views.%s)%s;
			}""" % (constant, varsextract, view.name.upper(), varsbuilder))

		elif match['keyword'] == "matchItem":
			typecases.append("\t\t\tcase %s:\n\t\t\t\treturn %s.CONTENT_ITEM_TYPE;" % (constant, targetTable))
			
			# when table, build normal query string
			# TODO: expand this to match any/all incoming []'s from path pattern
			if isinstance(target, Table):
				selectionCases.append("""
			case %s: {%s
				return builder.table(Tables.%s)%s;
			}""" % (constant, varsextract, target.name.upper(), varsbuilder))
			
			# when view, or table with queryWith, build separate query
			if queryWithView is not None:
				view = VIEWS_EXPORTED[queryWithView]
				querySelectionCases.append("""
			case %s: {%s
				return builder.table(Views.%s)%s;
			}""" % (constant, varsextract, view.name.upper(), varsbuilder))

	params['uriMatcherConstants'] = "\n".join(constants)
	params['uriMatcherBuilder'] = "\n".join(builders)
	params['getTypeCases'] = "\n".join(typecases)
	
	params['insertCases'] = "".join(insertcases).strip("\n")
	
	params['buildQuerySelectionCases'] = "".join(querySelectionCases).strip("\n")
	params['buildSelectionCases'] = "".join(selectionCases).strip("\n")

	return string.Template("""
package ${package};

import java.util.List;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.UriMatcher;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.net.Uri;

import ${package}.${contractClass}.*;

public abstract class ${providerClass} extends ContentProvider {
	private SQLiteOpenHelper mOpenHelper;

	interface Tables {
${tableNames}
	}

	interface Views {
${viewNames}
	}

${uriMatcherConstants}

	private static final UriMatcher sUriMatcher = buildUriMatcher();

	private static UriMatcher buildUriMatcher() {
		final UriMatcher matcher = new UriMatcher(UriMatcher.NO_MATCH);
		final String authority = SessionsContract.CONTENT_AUTHORITY;

${uriMatcherBuilder}

		return matcher;
	}
    
	@Override
	public boolean onCreate() {
		// TODO: create database instance here
		return true;
	}

	@Override
	public String getType(Uri uri) {
		final int match = sUriMatcher.match(uri);
		switch (match) {
${getTypeCases}
			default:
				throw new UnsupportedOperationException("Unknown uri: " + uri);
		}
	}

	@Override
	public Cursor query(Uri uri, String[] projection, String selection, String[] selectionArgs, String sortOrder) {
		final SQLiteDatabase db = mOpenHelper.getReadableDatabase();
		final SelectionBuilder builder = buildQuerySelection(uri);
		return builder.where(selection, selectionArgs).query(db, projection, sortOrder);
	}

	@Override
	public Uri insert(Uri uri, ContentValues values) {
		final SQLiteDatabase db = mOpenHelper.getWritableDatabase();
		final int match = sUriMatcher.match(uri);
		switch (match) {
${insertCases}
			default: {
				throw new UnsupportedOperationException("Unknown uri: " + uri);
			}
		}
	}

	@Override
	public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
		final SQLiteDatabase db = mOpenHelper.getWritableDatabase();
		final SelectionBuilder builder = buildSelection(uri);
		return builder.where(selection, selectionArgs).update(db, values);
	}

	@Override
	public int delete(Uri uri, String selection, String[] selectionArgs) {
		final SQLiteDatabase db = mOpenHelper.getWritableDatabase();
		final SelectionBuilder builder = buildSelection(uri);
		return builder.where(selection, selectionArgs).delete(db);
	}

	private SelectionBuilder buildQuerySelection(Uri uri) {
		final SelectionBuilder builder = new SelectionBuilder();
		final List<String> paths = uri.getPathSegments();
		final int match = sUriMatcher.match(uri);
		switch (match) {
${buildQuerySelectionCases}
			default: {
				return buildSelection(uri, match, builder);
			}
		}
	}

	private SelectionBuilder buildSelection(Uri uri) {
		final SelectionBuilder builder = new SelectionBuilder();
		final int match = sUriMatcher.match(uri);
		return buildSelection(uri, match, builder);
	}

	private SelectionBuilder buildSelection(Uri uri, int match, SelectionBuilder builder) {
		final List<String> paths = uri.getPathSegments();
		switch (match) {
${buildSelectionCases}
			default: {
				throw new UnsupportedOperationException("Unknown uri: " + uri);
			}
		}
	}
}
""").substitute(params)



raw = open(INPUTSQL).read()

# find header information
header = HEADER.search(raw)
params = [ match.groupdict() for match in PARAM.finditer(header.group(1)) ]
for param in params:
	if param['keyword'] == "name":
		TARGETNAME = param['param1'].strip()
	elif param['keyword'] == "package":
		PACKAGE = param['param1'].strip()

print TARGETNAME, PACKAGE

# TODO: handle enum defs

TABLES = {}
TABLES_LIST = []
VIEWS = {}
VIEWS_LIST = []
VIEWS_EXPORTED = {}

for match in TABLE.finditer(raw):
	table = Table(match.groupdict())
	TABLES[table.name] = table
	TABLES_LIST.append(table)

for match in VIEW.finditer(raw):
	view = View(match.groupdict())
	VIEWS[view.name] = view
	VIEWS_LIST.append(view)
	if view.exportAs is not None:
		VIEWS_EXPORTED[view.exportAs] = view

with open("%sContract.java" % (TARGETNAME), 'w') as f:
	f.write(contract())
with open("Abstract%sProvider.java" % (TARGETNAME), 'w') as f:
	f.write(provider())






