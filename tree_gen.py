"""
Simple Tree Generator for ECUC Parameter Definitions
Takes an ARXML paramdef file as input and generates simple and detailed tree representations.
@author: GUU8HC
"""

import os
import sys
import json

# Add parent directory to Python path to import env module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Parameter:
    """Simple parameter representation"""
    name: str
    param_type: str
    multiplicity: str
    description: str = ""
    default_value: str = ""
    min_value: str = ""
    max_value: str = ""
    literals: List[str] = None
    
    def __post_init__(self):
        if self.literals is None:
            self.literals = []


@dataclass
class Reference:
    """Simple reference representation"""
    name: str
    ref_type: str
    multiplicity: str
    description: str = ""
    destinations: List[str] = None
    
    def __post_init__(self):
        if self.destinations is None:
            self.destinations = []


@dataclass
class Container:
    """Simple container representation"""
    name: str
    container_type: str
    multiplicity: str
    description: str = ""
    config_classes: List[str] = None
    parameters: List[Parameter] = None
    references: List[Reference] = None
    sub_containers: List['Container'] = None
    
    def __post_init__(self):
        if self.config_classes is None:
            self.config_classes = []
        if self.parameters is None:
            self.parameters = []
        if self.references is None:
            self.references = []
        if self.sub_containers is None:
            self.sub_containers = []


@dataclass
class Module:
    """Simple module representation"""
    name: str
    description: str = ""
    category: str = ""
    version: str = ""
    containers: List[Container] = None
    
    def __post_init__(self):
        if self.containers is None:
            self.containers = []


class SimpleARXMLParser:
    """Simple ARXML parser for ECUC parameter definitions"""
    
    def __init__(self):
        self.ns = {
            'ar': 'http://autosar.org/schema/r4.0'
        }
    
    def parse_arxml_file(self, file_path: str) -> Module:
        """Parse ARXML file and extract module structure"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Find ECUC module or destination URI definition
            module_def = root.find('.//ar:ECUC-MODULE-DEF', self.ns)
            if module_def is None:
                # Try to find ECUC-DESTINATION-URI-DEF and get the sub-container definitions
                dest_def = root.find('.//ar:ECUC-DESTINATION-URI-DEF', self.ns)
                if dest_def is not None:
                    # For destination URI def, extract the module config container
                    module_conf = dest_def.find('.//ar:ECUC-PARAM-CONF-CONTAINER-DEF', self.ns)
                    if module_conf is not None:
                        module_def = module_conf
            
            if module_def is None:
                raise ValueError("No ECUC-MODULE-DEF or ECUC-PARAM-CONF-CONTAINER-DEF found in the file")
            
            # Extract module information
            module = Module(
                name=self._get_text(module_def, 'ar:SHORT-NAME'),
                description=self._get_text(module_def, 'ar:DESC/ar:L-2[@L="EN"]', default=""),
                category=self._get_text(module_def, 'ar:CATEGORY'),
                version=self._get_text(module_def, 'ar:VERSION')
            )
            
            # Parse containers - look for sub-containers which contain the actual definitions
            sub_containers_elem = module_def.find('ar:SUB-CONTAINERS', self.ns)
            if sub_containers_elem is not None:
                for container_elem in sub_containers_elem.findall('ar:ECUC-PARAM-CONF-CONTAINER-DEF', self.ns):
                    container = self._parse_container(container_elem)
                    module.containers.append(container)
            
            # Also look for direct CONTAINERS element
            containers_elem = module_def.find('ar:CONTAINERS', self.ns)
            if containers_elem is not None:
                for container_elem in containers_elem.findall('ar:ECUC-PARAM-CONF-CONTAINER-DEF', self.ns):
                    container = self._parse_container(container_elem)
                    module.containers.append(container)
            
            return module
            
        except Exception as e:
            raise Exception(f"Error parsing ARXML file: {e}")
    
    def _parse_container(self, container_elem) -> Container:
        """Parse container element"""
        container = Container(
            name=self._get_text(container_elem, 'ar:SHORT-NAME'),
            container_type="CONTAINER",
            multiplicity=self._get_multiplicity(container_elem),
            description=self._get_text(container_elem, 'ar:DESC/ar:L-2[@L="EN"]', default="")
        )
        
        # Parse parameters
        params_elem = container_elem.find('ar:PARAMETERS', self.ns)
        if params_elem is not None:
            for param_elem in params_elem:
                param = self._parse_parameter(param_elem)
                container.parameters.append(param)
        
        # Parse references
        refs_elem = container_elem.find('ar:REFERENCES', self.ns)
        if refs_elem is not None:
            for ref_elem in refs_elem:
                ref = self._parse_reference(ref_elem)
                container.references.append(ref)
        
        # Parse sub-containers
        sub_containers_elem = container_elem.find('ar:SUB-CONTAINERS', self.ns)
        if sub_containers_elem is not None:
            for sub_elem in sub_containers_elem:
                sub_container = self._parse_container(sub_elem)
                sub_container.container_type = "SUB_CONTAINER"
                container.sub_containers.append(sub_container)
        
        # Parse choice containers
        choices_elem = container_elem.find('ar:CHOICES', self.ns)
        if choices_elem is not None:
            for choice_elem in choices_elem:
                choice_container = self._parse_container(choice_elem)
                choice_container.container_type = "CHOICE_CONTAINER"
                container.sub_containers.append(choice_container)
        
        return container
    
    def _parse_parameter(self, param_elem) -> Parameter:
        """Parse parameter element"""
        param_type = param_elem.tag.split('}')[-1] if '}' in param_elem.tag else param_elem.tag
        
        # Map ECUC parameter types to simple types
        type_mapping = {
            'ECUC-BOOLEAN-PARAM-DEF': 'BOOLEAN',
            'ECUC-INTEGER-PARAM-DEF': 'INTEGER',
            'ECUC-FLOAT-PARAM-DEF': 'FLOAT',
            'ECUC-STRING-PARAM-DEF': 'STRING',
            'ECUC-ENUMERATION-PARAM-DEF': 'ENUMERATION',
            'ECUC-FUNCTION-NAME-DEF': 'FUNCTION_NAME'
        }
        
        param = Parameter(
            name=self._get_text(param_elem, 'ar:SHORT-NAME'),
            param_type=type_mapping.get(param_type, 'UNKNOWN'),
            multiplicity=self._get_multiplicity(param_elem),
            description=self._get_text(param_elem, 'ar:DESC/ar:L-2[@L="EN"]', default=""),
            default_value=self._get_text(param_elem, 'ar:DEFAULT-VALUE', default=""),
            min_value=self._get_text(param_elem, 'ar:MIN', default=""),
            max_value=self._get_text(param_elem, 'ar:MAX', default="")
        )
        
        # Get enumeration literals
        literals_elem = param_elem.find('ar:LITERALS', self.ns)
        if literals_elem is not None:
            for literal_elem in literals_elem.findall('ar:ECUC-ENUMERATION-LITERAL-DEF', self.ns):
                literal_name = self._get_text(literal_elem, 'ar:SHORT-NAME')
                if literal_name:
                    param.literals.append(literal_name)
        
        return param
    
    def _parse_reference(self, ref_elem) -> Reference:
        """Parse reference element"""
        ref_type = ref_elem.tag.split('}')[-1] if '}' in ref_elem.tag else ref_elem.tag
        
        # Map ECUC reference types
        type_mapping = {
            'ECUC-REFERENCE-DEF': 'REFERENCE',
            'ECUC-CHOICE-REFERENCE-DEF': 'CHOICE_REFERENCE',
            'ECUC-FOREIGN-REFERENCE-DEF': 'FOREIGN_REFERENCE'
        }
        
        ref = Reference(
            name=self._get_text(ref_elem, 'ar:SHORT-NAME'),
            ref_type=type_mapping.get(ref_type, 'REFERENCE'),
            multiplicity=self._get_multiplicity(ref_elem),
            description=self._get_text(ref_elem, 'ar:DESC/ar:L-2[@L="EN"]', default="")
        )
        
        # Get destination references
        dest_elem = ref_elem.find('ar:DESTINATION-REF', self.ns)
        if dest_elem is not None:
            dest_text = dest_elem.text
            if dest_text:
                ref.destinations.append(dest_text)
        
        return ref
    
    def _get_multiplicity(self, elem) -> str:
        """Extract multiplicity from element"""
        lower = self._get_text(elem, 'ar:LOWER-MULTIPLICITY', default="1")
        upper = self._get_text(elem, 'ar:UPPER-MULTIPLICITY', default="1")
        
        if upper == "*":
            return f"{lower}..*"
        elif lower == upper:
            return lower
        else:
            return f"{lower}..{upper}"
    
    def _get_text(self, parent, xpath: str, default: str = "") -> str:
        """Get text content from XML element"""
        if parent is None:
            return default
        
        elem = parent.find(xpath, self.ns)
        if elem is not None and elem.text:
            return elem.text.strip()
        return default


class JSONGenerator:
    """Generate JSON representations with parent-child relationships preserved"""
    
    def __init__(self, module: Module):
        self.module = module
    
    def generate_json(self) -> dict:
        """Generate nested JSON structure preserving parent-child relationships"""
        module_dict = {
            "name": self.module.name,
            "type": "MODULE",
            "description": self.module.description,
            "category": self.module.category,
            "version": self.module.version,
            "containers": []
        }
        
        for container in self.module.containers:
            module_dict["containers"].append(self._container_to_dict(container))
        
        return module_dict
    
    def _container_to_dict(self, container: Container) -> dict:
        """Convert container to dictionary with children"""
        container_dict = {
            "name": container.name,
            "type": container.container_type,
            "multiplicity": container.multiplicity,
            "description": container.description,
            "lowerMultiplicity": self._extract_lower_multiplicity(container.multiplicity),
            "upperMultiplicity": self._extract_upper_multiplicity(container.multiplicity),
            "parameters": [],
            "references": [],
            "sub_containers": []
        }
        
        for param in container.parameters:
            container_dict["parameters"].append(self._parameter_to_dict(param))
        
        for ref in container.references:
            container_dict["references"].append(self._reference_to_dict(ref))
        
        for sub_container in container.sub_containers:
            container_dict["sub_containers"].append(self._container_to_dict(sub_container))
        
        return container_dict
    
    def _parameter_to_dict(self, param: Parameter) -> dict:
        """Convert parameter to dictionary"""
        return {
            "name": param.name,
            "type": param.param_type,
            "multiplicity": param.multiplicity,
            "description": param.description,
            "default": param.default_value,
            "min": param.min_value,
            "max": param.max_value,
            "literals": param.literals
        }
    
    def _reference_to_dict(self, ref: Reference) -> dict:
        """Convert reference to dictionary"""
        return {
            "name": ref.name,
            "type": ref.ref_type,
            "multiplicity": ref.multiplicity,
            "description": ref.description,
            "destinations": ref.destinations
        }
    
    def _extract_lower_multiplicity(self, multiplicity: str) -> int:
        """Extract lower multiplicity value"""
        if not multiplicity:
            return 1
        try:
            return int(multiplicity.split('.')[0])
        except:
            return 1
    
    def _extract_upper_multiplicity(self, multiplicity: str) -> int:
        """Extract upper multiplicity value, return -1 for infinite"""
        if not multiplicity:
            return 1
        try:
            if '..*' in multiplicity:
                return -1
            parts = multiplicity.split('..')
            if len(parts) > 1:
                return int(parts[1])
            return int(multiplicity.split('.')[0])
        except:
            return 1


class SimpleTreeGenerator:
    """Generate tree representations from parsed module"""
    
    def __init__(self, module: Module):
        self.module = module
    
    def generate_simple_tree(self) -> str:
        """Generate simple ASCII tree"""
        lines = []
        lines.append(f"{self.module.name} [MODULE]")
        lines.append(f"└─ {self.module.description}")
        
        for i, container in enumerate(self.module.containers):
            is_last = i == len(self.module.containers) - 1
            self._add_container_to_tree(lines, container, "", is_last, include_details=False)
        
        return "\n".join(lines)
    
    def generate_detailed_tree(self) -> str:
        """Generate detailed ASCII tree"""
        lines = []
        lines.append(f"{self.module.name} [MODULE]")
        lines.append(f"└─ {self.module.description}")
        lines.append(f"   ├─ Category: {self.module.category}")
        lines.append(f"   ├─ Version: {self.module.version}")
        
        for i, container in enumerate(self.module.containers):
            is_last = i == len(self.module.containers) - 1
            prefix = "    "
            self._add_container_to_tree(lines, container, prefix, is_last, include_details=True)
        
        return "\n".join(lines)
    
    def _add_container_to_tree(self, lines: List[str], container: Container, 
                             prefix: str, is_last: bool, include_details: bool):
        """Add container to tree lines"""
        current_prefix = "└── " if is_last else "├── "
        lines.append(f"{prefix}{current_prefix}{container.name} [{container.container_type}] {container.multiplicity}")
        
        next_prefix = prefix + ("    " if is_last else "│   ")
        
        if container.description:
            lines.append(f"{next_prefix}└─ {container.description}")
        
        if include_details and container.config_classes:
            lines.append(f"{next_prefix}├─ Config: {', '.join(container.config_classes)}")
        
        # Count total items
        total_items = len(container.parameters) + len(container.references) + len(container.sub_containers)
        current_item = 0
        
        # Add parameters
        for param in container.parameters:
            current_item += 1
            is_last_item = current_item == total_items
            self._add_parameter_to_tree(lines, param, next_prefix, is_last_item, include_details)
        
        # Add references
        for ref in container.references:
            current_item += 1
            is_last_item = current_item == total_items
            self._add_reference_to_tree(lines, ref, next_prefix, is_last_item, include_details)
        
        # Add sub-containers
        for sub_container in container.sub_containers:
            current_item += 1
            is_last_item = current_item == total_items
            self._add_container_to_tree(lines, sub_container, next_prefix, is_last_item, include_details)
    
    def _add_parameter_to_tree(self, lines: List[str], param: Parameter, 
                             prefix: str, is_last: bool, include_details: bool):
        """Add parameter to tree lines"""
        current_prefix = "└── " if is_last else "├── "
        param_info = f"{param.name} [{param.param_type}] {param.multiplicity}"
        
        if include_details:
            if param.default_value:
                param_info += f" = {param.default_value}"
            if param.min_value or param.max_value:
                param_info += f" ({param.min_value}..{param.max_value})"
        
        lines.append(f"{prefix}{current_prefix}📊 {param_info}")
        
        if include_details:
            next_prefix = prefix + ("    " if is_last else "│   ")
            if param.description:
                lines.append(f"{next_prefix}└─ {param.description}")
            if param.literals:
                values_text = ', '.join(param.literals[:5])
                if len(param.literals) > 5:
                    values_text += "..."
                lines.append(f"{next_prefix}└─ Values: {values_text}")
    
    def _add_reference_to_tree(self, lines: List[str], ref: Reference, 
                             prefix: str, is_last: bool, include_details: bool):
        """Add reference to tree lines"""
        current_prefix = "└── " if is_last else "├── "
        ref_info = f"{ref.name} [{ref.ref_type}] {ref.multiplicity}"
        lines.append(f"{prefix}{current_prefix}🔗 {ref_info}")
        
        if include_details:
            next_prefix = prefix + ("    " if is_last else "│   ")
            if ref.description:
                lines.append(f"{next_prefix}├─ {ref.description}")
            if ref.destinations:
                for i, dest in enumerate(ref.destinations[:3]):
                    dest_short = dest.split('/')[-1] if '/' in dest else dest
                    is_last_dest = i == len(ref.destinations[:3]) - 1 and len(ref.destinations) <= 3
                    dest_prefix = "└─" if is_last_dest else "├─"
                    lines.append(f"{next_prefix}{dest_prefix} → {dest_short}")
                if len(ref.destinations) > 3:
                    lines.append(f"{next_prefix}└─ ... and {len(ref.destinations) - 3} more")


class JSONGenerator:
    """Generate JSON representation from parsed module"""
    
    def __init__(self, module: Module):
        self.module = module
    
    def generate_json(self) -> dict:
        """Generate JSON representation of the module matching com_paramdef.json format"""
        containers_dict = {}
        for container in self.module.containers:
            containers_dict[container.name] = self._container_to_json(container)
        
        return {
            self.module.name: containers_dict
        }
    
    def _container_to_json(self, container: Container) -> dict:
        """Convert container to JSON dict with simplified format matching com_paramdef.json"""
        container_dict = {}
        
        # Add parameters as direct dictionary keys
        for param in container.parameters:
            container_dict[param.name] = self._parameter_to_json(param)
        
        # Add sub-containers as nested dictionaries
        for sub in container.sub_containers:
            container_dict[sub.name] = self._container_to_json(sub)
        
        return container_dict
    
    def _parameter_to_json(self, param: Parameter) -> dict:
        """Convert parameter to JSON dict with simplified format"""
        param_dict = {}
        
        # Add type if available
        if param.param_type:
            param_dict["type"] = param.param_type
        
        # Add multiplicity if it's not the default "1"
        if param.multiplicity and param.multiplicity != "1":
            param_dict["multiplicity"] = param.multiplicity
        
        # Add options/literals for enums
        if param.literals:
            param_dict["options"] = param.literals
        
        # Add value constraints
        if param.min_value:
            param_dict["minValue"] = param.min_value
        if param.max_value:
            param_dict["maxValue"] = param.max_value
        if param.default_value:
            param_dict["default"] = param.default_value
        
        # Add description if available
        if param.description:
            param_dict["description"] = param.description
        
        # Return empty dict if no attributes (to match com_paramdef.json style)
        return param_dict if param_dict else {}
    
    def _reference_to_json(self, ref: Reference) -> dict:
        """Convert reference to JSON dict"""
        ref_dict = {
            "type": ref.ref_type,
            "multiplicity": ref.multiplicity,
            "description": ref.description
        }
        
        if ref.destinations:
            ref_dict["destinations"] = ref.destinations
        
        return ref_dict


def convert_paramdef_to_json(arxml_file) -> dict:
    parser_obj = SimpleARXMLParser()
    module = parser_obj.parse_arxml_file(arxml_file)
    
    json_gen = JSONGenerator(module=module)
    return json_gen.generate_json()


def main():
    """Main function to generate tree files from ARXML input"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate JSON/tree from ARXML parameter definitions")
    parser.add_argument("arxml_file", help="Path to ARXML parameter definition file")
    parser.add_argument("-o", "--output", help="Output file path (JSON). If not specified, prints to stdout", default=None)
    parser.add_argument("--format", choices=["nested", "flat", "both"], default="nested",
                       help="Output format: nested (default) | flat | both")
    
    args = parser.parse_args()
    arxml_file = args.arxml_file
    output_file = args.output
    output_format = args.format
    
    try:
        # Parse ARXML file
        print(f"Parsing ARXML file: {arxml_file}", file=sys.stderr)
        parser_obj = SimpleARXMLParser()
        module = parser_obj.parse_arxml_file(arxml_file)
        
        json_gen = JSONGenerator(module=module)
        json_data = json_gen.generate_json()
        
        # Convert to JSON string with pretty formatting
        json_str = json.dumps(json_data, indent=2, ensure_ascii=False)
        
        # Output JSON
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(json_str)
            print(f"Wrote JSON to {output_file}", file=sys.stderr)
        else:
            print(json_str)
        
        # Print summary to stderr
        total_containers = len(module.containers)
        total_params = sum(len(c.parameters) for c in module.containers)
        total_refs = sum(len(c.references) for c in module.containers)
        
        print(f"\nModule Summary:", file=sys.stderr)
        print(f"  Name: {module.name}", file=sys.stderr)
        print(f"  Containers: {total_containers}", file=sys.stderr)
        print(f"  Parameters: {total_params}", file=sys.stderr)
        print(f"  References: {total_refs}", file=sys.stderr)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
