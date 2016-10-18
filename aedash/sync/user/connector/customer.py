class CustomerConnector(object):    
    def __init__(self, implementation, options = {}):
        '''
        :type options: dict
        '''
        self.implementation = implementation
        
        required_functions = ['connector_metadata', 'connector_initialize']
        for required_function in required_functions:
            if (not hasattr(implementation, required_function)):
                raise Exception('Missing function: %s source: %s' % (required_function, implementation.__file__))            
 
        self.metadata = metadata = implementation.connector_metadata()        
        if (metadata.get('name') == None):
            raise Exception('Missing metadata property: %s source: %s' % ('name', implementation.__file__))
            
        required_options = metadata.get('required_options')
        if (required_options != None):
            for required_option in required_options:
                if not(required_option in options):
                    raise Exception('Missing setting: %s connector: %s' % (required_option, metadata['name']))
        self.state = implementation.connector_initialize(options)
        
    def get_users_with_groups(self, groups):
        return self.implementation.connector_get_users_with_groups(self.state, groups)        

    def is_existing_username(self, username):
        return self.implementation.connector_is_existing_username(self.state, username)  