import sys
import uuid

description = "Create an empty, properly configured .csproj file."
command_group = "Developer tools"

TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="4.0" DefaultTargets="WafBuild" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Configuration Condition=" '$(Configuration)' == '' ">Debug</Configuration>
    <Platform Condition=" '$(Platform)' == '' ">AnyCPU</Platform>
    <ProductVersion>8.0.30703</ProductVersion>
    <SchemaVersion>2.0</SchemaVersion>
    <ProjectGuid>{{{projectguid}}}</ProjectGuid>
    <OutputType>Library</OutputType>
    <AppDesignerFolder>Properties</AppDesignerFolder>
    <RootNamespace>{rootnamespace}</RootNamespace>
    <AssemblyName>{assemblyname}</AssemblyName>
    <TargetFrameworkVersion>v4.0</TargetFrameworkVersion>
    <FileAlignment>512</FileAlignment>
    <TargetFrameworkProfile>Client</TargetFrameworkProfile>
  </PropertyGroup>
  <Import Project="..\\SharedSettings.target" />
  <PropertyGroup>
    <StartupObject />
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="System" />
    <Reference Include="System.Core" />
    <Reference Include="System.Xml.Linq" />
    <Reference Include="System.Data.DataSetExtensions" />
    <Reference Include="System.Data" />
    <Reference Include="System.Xml" />
  </ItemGroup>
  <ItemGroup>
    <Compile Include="./**/*.cs" />
  </ItemGroup>
  <ItemGroup />
  <Import Project="$(MSBuildToolsPath)\\Microsoft.CSharp.targets" />
  <!-- To modify your build process, add your task inside one of the targets below and uncomment it. 
       Other similar extension points exist, see Microsoft.Common.targets.
  <Target Name="BeforeBuild">
  </Target>
  <Target Name="AfterBuild">
  </Target>
  -->
</Project>"""

HELP_SYNONYMS = ["--help", "-h", "/h", "/help", "/?", "-?", "h", "help"]

def main():
    UUID = str(uuid.uuid4()).upper()
    if not (2<=len(sys.argv)<=3) or (len(sys.argv)>=2 and sys.argv[1] in HELP_SYNONYMS):
        print "Usage:"
        print "    make_csproj.py <assemblyname> [<rootnamespace>]"
        print
        print "Create a new empty csproj with the specified assembly name. If <rootnamespace> is not"
        print "specified it defaults to <assemblyname>."
        sys.exit(1)
    assemblyname = sys.argv[1]
    rootnamespace = assemblyname if len(sys.argv) < 3 else sys.argv[2]
    print TEMPLATE.format(
            projectguid=UUID,
            rootnamespace=rootnamespace,
            assemblyname=assemblyname)

if __name__ == "__main__":
    main()
