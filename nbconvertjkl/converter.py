import glob
import os
import re
import logging
import sys
import nbformat

from traitlets.config import Config
from nbconvert import HTMLExporter
from shutil import copyfile

#TODO add validation and error checking throughout
#TODO cleanup logging
#TODO cleanup return values
#TODO use fname instead of title for dict keys (guarunteed to be different)

class Converter:


    def __init__(self, config_dict, new_nbs=None, existing_nbs=None):
        ''' The converter workhorse '''
        self.conf = config_dict
        self.logger = logging.getLogger(__name__)

        self.new_nbs = new_nbs or self.collect_new_nbs()
        self.existing_nbs = existing_nbs or self.collect_existing_nbs()


    def collect_existing_nbs(self):
        """ Collects existing notebooks from site notebooks folder """
        
        self.logger.debug("Getting existing notebook files: {}".format(self.conf['nb_write_path']))
        
        nb_file_paths = glob.glob(self.conf['nb_write_path'] + '*')
        nb_file_paths.sort()

        self.logger.debug("Found: {}".format(len(nb_file_paths)))
        
        return nb_file_paths


    def collect_new_nbs(self):
        """ Return sorted dictionary of notebooks """

        self.logger.debug("Getting notebook files from {}".format(self.conf['nb_read_path']))

        nb_file_paths = glob.glob(self.conf['nb_read_path'] + '*.ipynb')
        nb_file_paths.sort()

        self.logger.debug("Found: {}".format(len(nb_file_paths)))

        nbs = {}
        for nb_path in nb_file_paths:
            self.logger.debug("\nGathering notebook: {}".format(nb_path))
            
            new_nb = {}
            new_nb['fname'] = nb_path.split("/")[-1][:-6]
            new_nb['skip_build'] = False
            new_nb['read_path'] = self.conf['nb_read_path']
            new_nb['write_path'] = self.conf['nb_write_path']
            new_nb['nbnode'] = self.get_nbnode(nb_path)

            new_nb['body'] = self.get_body(new_nb['nbnode'])
            new_nb['topics'] = self.get_topics(new_nb['nbnode'])
            new_nb['title'] = self.get_title(new_nb['nbnode'])
            new_nb['permalink'] = self.get_permalink(new_nb['title'])

            new_nb['nav'] = None
            new_nb['info'] = "{{site.nb_info}}"

            new_nb['front_matter'] = self.get_front_matter(new_nb['title'], new_nb['permalink'], new_nb['topics'])

            temp = {}
            temp[new_nb['title']] = new_nb
            nbs.update( temp )

        return nbs
    

    def get_summary(self):
        """ Print summary of nbs """

        self.logger.debug('Getting summary...')

        nbs_str = ""
        
        for k in self.new_nbs.keys():
            
            fname = self.new_nbs[k]['fname']

            if self.new_nbs[k]['skip_build']:
                nb_str = "\n\n{} -- SKIPPED".format(fname)
            
            else:
                fm = self.new_nbs[k]['front_matter']
                info = self.new_nbs[k]['info'] or ''
                nav = self.new_nbs[k]['nav'] or ''
                body = '<!--HTML BODY - not shown in preview...too long-->'
                nb_str = "\n\n{}.html\n{}\n{}\n{}\n{}".format(fname, fm, info, nav, body)
            
            nbs_str = nbs_str + nb_str

        return nbs_str

    
    def get_nbnode(self, nb_path):
        """ Returns the nbnode """
        return nbformat.read(nb_path, as_version=4)


    def get_body(self, nb_node):
        """ Get HTML body from notebook and fix links """

        self.logger.debug('Getting nb body...')

        # Setup html exporter template/configs
        html_exporter = HTMLExporter()
        html_exporter.template_file = 'basic'
 
        (body, resources) = html_exporter.from_notebook_node(nb_node)
        fixed_body = self.fix_links(body)
        return fixed_body


    def link_repl(self, matchobj):
        """ Replace src/link matchobj with corrected link """
        print("called repl: {}".format(matchobj.groups()))
        corrected_link = 'src={{{{ "/assets/{}" | relative_url }}}} '.format(matchobj.groups()[0])
        return corrected_link


    def fix_links(self, body):
        """ Find all local asset links and correct """
        s = '|'.join(self.conf['asset_subdirs'])
        regex = re.compile(r'(?:source|src)=\"(\/?(?:%s)\/[\w\d\-_\.]+)\"' % s, re.IGNORECASE)
        fixed_body = re.sub(regex, self.link_repl, body)
        return fixed_body


    def get_title(self, nb_node):
        """ Return notebook title """

        self.logger.debug('Getting nb title...')

        for cell in nb_node.cells:
            if cell.source.startswith('#'):
                title = cell.source[1:].splitlines()[0].strip()
                cleaned_title = re.sub(r'[^\w\s]', '', title)
                break

        return cleaned_title or ''


    def get_permalink(self, nb_title):
        """ Return notebook permalink """

        self.logger.debug('Getting nb permalink...')

        #TODO harden...check for special chars, etc
        permalink = nb_title.lower().replace(" ", "-")

        return permalink


    def get_topics(self, nb_node):
        """ Return notebook topics """

        self.logger.debug('Getting nb topics...')

        txt_src = nb_node.cells[0].source
        regex = r"\*\*Topics\sCovered\*\*([\\n\*\s]+[\w\s]+)+"
        m = re.search(regex, txt_src)
        if len(m.group()) != 0:
            topics = m.group().replace("**Topics Covered**\n* ", "").split("\n* ")
        else: 
            topics = ''

        return str(topics)

    
    def get_nb_nav(self, prev_key=None, next_key=None):
        """ Get html for notebook navigation """
        
        self.logger.debug("Getting nb nav...")

        nav_comment = '<!-- NAV -->'
        prev_nb = ''
        contents = '<a href="{{{{ "/" | relative_url }}}}">Contents</a>'
        next_nb = ''

        if prev_key != None:
            prev_title = self.new_nbs[prev_key]['title']
            prev_link = self.new_nbs[prev_key]['permalink']
            prev_nb = '&lt; <a href="{{{{ "{}" | relative_url }}}}">{}</a> | '.format(prev_link, prev_title)

        if next_key != None:
            next_title = self.new_nbs[next_key]['title']
            next_link = self.new_nbs[next_key]['permalink']
            next_nb = ' | <a href="{{{{ "{}" | relative_url }}}}">{}</a> &gt;'.format(next_link, next_title)

        nb_nav = '\n{}<p style="font-style:italic;font-size:smaller;">{}{}{}</p>'.format(nav_comment, prev_nb, contents, next_nb)
        return nb_nav
    
    def add_nb_nav(self):
        """ Add nav to all nbs in the build """

        self.logger.debug("Adding nb nav...")


        # List of keys of nbs to build
        build_keys = [k for k in self.new_nbs if not self.new_nbs[k]['skip_build']] 

        for i in range(len(build_keys)):
            curr_nb_key = build_keys[i]
            self.logger.debug("{}".format(self.new_nbs[curr_nb_key]['fname']))
            if i == 0:
                prev_nb_key = None
                next_nb_key = build_keys[i+1]
            elif i == len(build_keys)-1:
                prev_nb_key = build_keys[i-1]
                next_nb_key = None
            else:
                prev_nb_key = build_keys[i-1]
                next_nb_key = build_keys[i+1]

            self.new_nbs[curr_nb_key]['nav'] = self.get_nb_nav(prev_nb_key, next_nb_key)

        return True


    def get_front_matter(self, title, permalink, topics):
        """ Return front_matter string """

        self.logger.debug('Getting front matter...')

        layout = "notebook"
        fm = "---\nlayout: {}\ntitle: {}\npermalink: /{}/\ntopics: {}\n---\n".format(layout, title, permalink, topics)
        return fm

    
    def clean_write_dir(self):
        """ Remove files from the write directory in conf """
        
        self.logger.debug("Removing files from write dir...")

        files = glob.glob(self.conf['nb_write_path'] + '*')
        for f in files:
            os.remove(f)
            self.logger.debug("Removed: {}".format(f))
        
        return True
    
    
    def write_nbs(self):
        """ Write notebooks"""

        self.logger.debug("Writing notebooks...")

        for nbtitle in self.new_nbs.keys():

            self.logger.debug("{}".format(nbtitle))
            
            if not self.new_nbs[nbtitle]['skip_build']:
                with open(self.conf['nb_write_path'] + self.new_nbs[nbtitle]['fname'] + '.html', "w") as file:
                    
                    file.write(self.new_nbs[nbtitle]['front_matter'])
                    if self.new_nbs[nbtitle]['info']:
                        file.write(self.new_nbs[nbtitle]['info'])
                    if self.new_nbs[nbtitle]['nav']:
                        file.write(self.new_nbs[nbtitle]['nav'])
                    file.write(self.new_nbs[nbtitle]['body'])
                    self.logger.debug("Written.")    
            else:
                self.logger.debug("Skipped.")
        return True


    def copy_and_move_assets(self):
        """ Move assets (images, etc) from notebook folder to docs/assets folder """
        #TODO change so it doesn't overwrite by default
        # clean_write_dir should be run first cause it confirms with user
        

        for subdir in self.conf['asset_subdirs']:
            
            self.logger.debug("Looking in: {}".format(subdir))
            files = glob.glob(self.conf['nb_read_path'] + subdir + '/*')
            self.logger.debug("Found files: {}".format(files))
            
            for src in files:
                if os.path.isfile(src):
                    fname = src.split("/")[-1]
                    self.logger.debug("Copying file: {}...".format(fname))
                    fdest = self.conf['asset_write_path'] + subdir
                    if not os.path.exists(fdest):
                        os.makedirs(fdest)
                    copyfile(src, fdest + '/' + fname)

            return True


    def validate_front_matter(self, fm=None):
        """ Validate front_matter """
        #TODO
        return True